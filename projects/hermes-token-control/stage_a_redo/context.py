from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from .storage import Journal, Store, best_effort_notice, encode, sha256


@dataclass(frozen=True)
class Policy:
    compact_at: int = 48_000
    strong_at: int = 64_000
    result_bytes: int = 8192
    protect_recent_turns: int = 8

    def __post_init__(self) -> None:
        if not 0 < self.compact_at <= self.strong_at or self.result_bytes < 1 or self.protect_recent_turns < 1:
            raise ValueError("invalid advisory policy")


@dataclass(frozen=True)
class Checkpoint:
    # Created by a trusted host state builder, not by a model-provided list.
    capsule_sha256: str
    covered_turn_sha256: frozenset[str]


@dataclass(frozen=True)
class Prepared:
    payload: dict[str, Any]
    actions: tuple[str, ...]
    estimated_tokens: int | None
    segment_requested: bool


def closed_turn(turn: list[dict[str, Any]]) -> bool:
    pending: set[str] = set()
    used: set[str] = set()
    if not turn or turn[0].get("role") != "user":
        return False
    for index, message in enumerate(turn):
        role = message.get("role")
        if role not in ("user", "assistant", "tool") or (role == "user" and index != 0):
            return False
        if role == "assistant":
            if pending:
                return False
            for call in message.get("tool_calls", []):
                identity = call.get("id")
                if not isinstance(identity, str) or not identity or identity in used:
                    return False
                pending.add(identity)
                used.add(identity)
        elif role == "tool":
            identity = message.get("tool_call_id")
            if identity not in pending:
                return False
            pending.remove(identity)
    return not pending and turn[-1].get("role") == "assistant" and not turn[-1].get("tool_calls")


def archive_result(content: str, metadata: dict[str, Any], store: Store,
                   threshold_bytes: int = 8192) -> str:
    """Call inside the existing tool adapter, before its result enters history.

    metadata is derived from the actual process/HTTP/test result, never an LLM.
    Failures retain status, exact exit code and failed IDs in the inline manifest.
    Any archive failure must be caught by the host's pass-through result adapter.
    """
    data = content.encode("utf-8")
    if len(data) <= threshold_bytes:
        return content
    if metadata.get("status") not in ("OK", "FAILED", "UNKNOWN"):
        raise ValueError("tool result requires an explicit status")
    if "exit_code" not in metadata or metadata["exit_code"] is not None and type(metadata["exit_code"]) is not int:
        raise ValueError("tool exit code missing/invalid")
    failures = metadata.get("failed_ids")
    if not isinstance(failures, list) or any(not isinstance(x, str) for x in failures):
        raise ValueError("explicit failed_ids required")
    artifact = store.put(data)
    manifest = {"kind": "artifact-manifest", **artifact,
                "status": metadata["status"], "exit_code": metadata["exit_code"],
                "failed_ids": failures, "read": {"offset": 0, "length": 4096},
                "note": "完整证据已归档；需要细节时按 sha256 与 byte range 读取，不重跑工具。"}
    return encode(manifest).decode()


def prepare(payload: dict[str, Any], *, store: Store,
            counter: Callable[[dict[str, Any]], int],
            checkpoint: Checkpoint | None = None,
            verify_checkpoint: Callable[[Checkpoint], bool] | None = None,
            tool_metadata: dict[str, dict[str, Any]] | None = None,
            policy: Policy = Policy()) -> Prepared:
    """Representation-only pass-through on any governance failure.

    Supported projection: JSON Chat-Completions-style message arrays. Signed
    reasoning/Responses/other formats are passed unchanged, not converted.
    Counter observes the complete provider payload, including tools/framing.
    """
    actions: list[str] = []
    try:
        tokens = counter(payload)
        if type(tokens) is not int or tokens < 0:
            raise ValueError("unknown token count")
    except Exception:
        return Prepared(payload, ("COUNTER_UNAVAILABLE_SEND_ORIGINAL",), None, False)
    if tokens < policy.compact_at:
        return Prepared(payload, (), tokens, False)
    try:
        # Never mutate input in-place: failed compaction returns the original.
        store.put_json(payload)
        actions.append("ARCHIVED_ORIGINAL")
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return Prepared(payload, tuple(actions + ["UNSUPPORTED_FORMAT_SEND_ORIGINAL"]), tokens, tokens >= policy.strong_at)
        prefix, turns = [], []
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("unsupported message shape")
            role = message.get("role")
            allowed_fields = {
                "system": {"role", "content", "name"},
                "developer": {"role", "content", "name"},
                "user": {"role", "content", "name"},
                "assistant": {"role", "content", "name", "tool_calls", "refusal"},
                "tool": {"role", "content", "tool_call_id"},
            }
            # Unknown extension fields may carry signed reasoning or other
            # provider-owned replay state. Multimodal content is likewise not
            # projected by this text-only adapter. Preserve the entire request.
            if role not in allowed_fields or not set(message) <= allowed_fields[role]:
                raise ValueError("provider-specific message state: preserve original")
            if message.get("content") is not None and not isinstance(message["content"], str):
                raise ValueError("non-text content: preserve original")
            if role in ("system", "developer"):
                if turns:
                    raise ValueError("mid-history policy message: preserve original")
                prefix.append(message)
            elif role == "user":
                turns.append([message])
            elif turns:
                turns[-1].append(message)
            else:
                raise ValueError("unsupported message sequence")
        if not turns:
            return Prepared(payload, tuple(actions), tokens, tokens >= policy.strong_at)
        projected = copy.deepcopy(turns)
        # Last/current turn remains byte-for-byte identical. New tool results
        # should already have gone through archive_result at the producer edge.
        for index, turn in enumerate(turns[:-1]):
            if not closed_turn(turn):
                continue
            for n, message in enumerate(turn):
                metadata = (tool_metadata or {}).get(message.get("tool_call_id", ""))
                if message.get("role") == "tool" and isinstance(message.get("content"), str) and metadata is not None:
                    compact = archive_result(message["content"], metadata, store, policy.result_bytes)
                    if compact != message["content"]:
                        projected[index][n]["content"] = compact
                        actions.append("RESULT_MANIFEST")
        capsule = None
        covered: frozenset[str] = frozenset()
        if checkpoint is not None and verify_checkpoint is not None and verify_checkpoint(checkpoint) is True:
            capsule = store.get(checkpoint.capsule_sha256).decode("utf-8")
            covered = checkpoint.covered_turn_sha256
        kept, removed = [], 0
        recent_start = max(1, len(turns) - policy.protect_recent_turns)
        for index, original in enumerate(turns):
            identity = sha256(encode(original))
            if 0 < index < recent_start and closed_turn(original) and identity in covered:
                # Matching archive is required in addition to trusted coverage.
                if store.get(identity) != encode(original):
                    raise ValueError("covered turn archive mismatch")
                removed += 1
            else:
                kept.append(projected[index])
        if removed:
            actions.append("CHECKPOINT_COVERED_TURNS_REMOVED")
            # Checkpoint has assistant provenance, never system/developer.
            kept.insert(1, [{"role": "assistant", "content": "已验证历史 checkpoint（资料，不是新指令）：\n" + str(capsule)}])
        result = dict(payload)
        result["messages"] = list(prefix) + [message for turn in kept for message in turn]
        new_tokens = counter(result)
        if type(new_tokens) is not int or new_tokens < 0:
            raise ValueError("unknown recount")
        if new_tokens >= tokens:
            result, new_tokens = payload, tokens
            actions.append("NO_GAIN_SEND_ORIGINAL")
        # This flag requests work slicing at a later safe task boundary. It is
        # NEVER permission to suppress or delay the present provider call.
        segment = new_tokens >= policy.strong_at
        if segment:
            actions.append("SEGMENT_ADVISORY_CONTINUE_SEND")
        return Prepared(result, tuple(actions), new_tokens, segment)
    except Exception:
        return Prepared(payload, tuple(actions + ["PROJECTION_FAILED_SEND_ORIGINAL"]), tokens, tokens >= policy.strong_at)


def dispatch(send: Callable[[dict[str, Any]], Any], payload: dict[str, Any], *,
             prepare_call: Callable[[dict[str, Any]], Prepared],
             audit: Callable[[str], None], journal: Journal | None = None,
             root_task_id: str = "unattributed") -> Any:
    """One invocation, one call to original sender. No retries or budget gates.

    Wire equivalent observational hooks to ALL real physical attempts in the
    host transport. SDK-internal retries cannot be inferred from this wrapper.
    """
    actual = payload
    try:
        candidate = prepare_call(copy.deepcopy(payload))
        actual = candidate.payload
        if candidate.actions:
            best_effort_notice(journal, "context:" + root_task_id, "context-advisory")
    except Exception:
        best_effort_notice(journal, "prepare:" + root_task_id, "governance-error")
    try:
        audit("attempt")
    except Exception:
        best_effort_notice(journal, "audit:" + root_task_id, "accounting-error")
    try:
        result = send(actual)
    except BaseException:
        try:
            audit("failed_or_cancelled")
        except Exception:
            best_effort_notice(journal, "audit:" + root_task_id, "accounting-error")
        raise
    try:
        audit("returned")
    except Exception:
        best_effort_notice(journal, "audit:" + root_task_id, "accounting-error")
    return result
