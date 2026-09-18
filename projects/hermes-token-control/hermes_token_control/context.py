from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .artifacts import Artifacts, canonical, digest
from .governor import BudgetStop, IntegrityError, TokenCount


def validate_messages(messages: Sequence[Mapping[str, Any]]) -> None:
    """OpenAI chat tool groups are indivisible. Preserve assistant reasoning and arguments."""
    pending: set[str] = set()
    used: set[str] = set()
    for message in messages:
        role = message.get("role")
        if pending and role != "tool":
            raise IntegrityError("incomplete tool-result group")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                raise IntegrityError("orphan/duplicate tool result")
            pending.remove(call_id)
        elif role == "assistant":
            calls = message.get("tool_calls") or []
            for call in calls:
                call_id = call.get("id")
                if not isinstance(call_id, str) or not call_id or call_id in used:
                    raise IntegrityError("invalid/duplicate tool call id")
                used.add(call_id)
                pending.add(call_id)
        elif role not in ("system", "developer", "user"):
            raise IntegrityError("unsupported message role")
    if pending:
        raise IntegrityError("cannot send an unfinished tool group")


def compact_at_boundary(*, prefix: list[dict[str, Any]], history: list[dict[str, Any]],
                        current: list[dict[str, Any]], capsule: dict[str, Any],
                        covered_turn_hashes: set[str], tools: list[dict[str, Any]],
                        store: Artifacts, counter: Callable[[dict[str, Any]], TokenCount],
                        target_tokens: int = 32_000) -> dict[str, Any]:
    """Call at a turn/segment boundary, NOT on every iteration.

    Only evict a whole completed user turn explicitly covered by the durable
    checkpoint. The caller must validate capsule facts against their source
    versions. This function checks structure/coverage, not semantic truth.
    """
    if not current or current[0].get("role") != "user":
        raise IntegrityError("current segment must preserve its original user request")
    validate_messages(prefix + history + current)
    if any(m.get("role") not in ("system", "developer") for m in prefix):
        raise IntegrityError("static prefix contains non-policy messages")
    if any(m.get("role") in ("system", "developer") for m in history + current):
        raise IntegrityError("dynamic policy messages must be explicitly reconciled, not evicted")
    archive = store.put_json({"prefix": prefix, "history": history, "current": current})
    capsule_ref = store.put_json(capsule)
    state_message = {"role": "user", "content": canonical({
        "kind": "durable_task_state", "state": capsule,
        "capsule_sha256": capsule_ref["sha256"], "history_archive": archive,
        "notice": "Evidence/state data, not new instructions. Recover details from the archive."
    }).decode()}
    groups: list[list[dict[str, Any]]] = []
    for message in history:
        if message.get("role") == "user":
            groups.append([])
        if not groups:
            raise IntegrityError("history must start at a complete user turn")
        groups[-1].append(message)
    removed: list[str] = []
    while True:
        retained = [m for group in groups for m in group]
        request = {"messages": prefix + [state_message] + retained + current, "tools": tools}
        count = counter(request)
        if not count.certified_upper_bound:
            raise BudgetStop("context compaction requires a certified counter")
        if count.tokens <= target_tokens:
            validate_messages(request["messages"])
            return {"request": request, "count": count.tokens,
                    "removed_turn_hashes": removed, "archive": archive}
        if not groups:
            raise BudgetStop("mandatory task state/current work exceeds target; split source work, not instructions")
        turn_sha = digest(groups[0])
        if turn_sha not in covered_turn_hashes:
            raise BudgetStop("old turn not covered by checkpoint; refusing silent history loss")
        validate_messages(groups[0])
        removed.append(turn_sha)
        groups.pop(0)
