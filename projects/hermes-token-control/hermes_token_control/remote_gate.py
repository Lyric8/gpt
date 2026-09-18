from __future__ import annotations

import fcntl
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .governor import IntegrityError


TERMINAL_COMPLETION_STATUSES = frozenset({"resolved", "rejected", "non-request"})
TERMINAL_GATE_STATUSES = frozenset({"REMOTE_COMPLETED", "NON_REQUEST"})
_STATUS_SHA = re.compile(r"\b[0-9a-f]{12,64}\b")
_STATUS_PATH = re.compile(r"(?:chat/)?to-(?:hermes|gpt)/[^`\s|）]+\.md")


@dataclass(frozen=True)
class GateDecision:
    status: str
    checked_at: str
    snapshot_commit: str
    source_path: str
    source_blob_sha: str
    source_message_id: str
    action_required: bool | None
    reply_required: bool | None
    completion_path: str | None = None
    completion_blob_sha: str | None = None
    completion_status: str | None = None
    status_row: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class RemoteStateError(IntegrityError):
    """Remote state cannot be proven safely enough to authorize an action."""


def _now_utc8() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _git(bare: Path, *args: str, max_stdout: int = 32 * 1024 * 1024) -> bytes:
    result = subprocess.run(
        ["git", "--git-dir=" + str(bare), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RemoteStateError(
            "git remote-state read failed: " + result.stderr[:2048].decode(errors="replace")
        )
    if len(result.stdout) > max_stdout:
        raise RemoteStateError("git remote-state output exceeds bounded read limit")
    return result.stdout


def _cat_blob(bare: Path, sha: str, *, max_bytes: int) -> bytes:
    raw_size = _git(bare, "cat-file", "-s", sha, max_stdout=256).decode("ascii").strip()
    try:
        size = int(raw_size)
    except ValueError as exc:
        raise RemoteStateError("invalid git blob size") from exc
    if size < 0 or size > max_bytes:
        raise RemoteStateError(f"remote-state blob exceeds {max_bytes} bytes")
    return _git(bare, "cat-file", "blob", sha, max_stdout=max_bytes + 1)


def _normalize_path(path: str) -> str:
    value = path.strip().strip("`")
    if value.startswith("to-hermes/") or value.startswith("to-gpt/"):
        value = "chat/" + value
    return value


def _parse_bool_metadata(text: str, key: str) -> bool | None:
    values: list[bool] = []
    prefix = key.lower() + ":"
    for raw in text.splitlines():
        line = raw.strip()
        if not line.lower().startswith(prefix):
            continue
        value = line.split(":", 1)[1].strip().lower()
        if value == "true":
            values.append(True)
        elif value == "false":
            values.append(False)
        else:
            raise RemoteStateError(f"invalid {key} metadata")
    if not values:
        return None
    if any(v != values[0] for v in values[1:]):
        raise RemoteStateError(f"conflicting {key} metadata")
    return values[0]


def _status_kind(value: str) -> str | None:
    if "✅ 已解决" in value:
        return "resolved"
    if "⛔ 不做" in value:
        return "rejected"
    if "➖ 非请求" in value or "➖ 通知件" in value:
        return "non-request"
    if "⏳ 待处理" in value:
        return "pending"
    if "🔧 处理中" in value:
        return "processing"
    return None


def _status_path(cell: str) -> str | None:
    match = _STATUS_PATH.search(cell)
    return _normalize_path(match.group(0)) if match else None


def _status_blob(cell: str) -> str | None:
    match = _STATUS_SHA.search(cell.lower())
    return match.group(0) if match else None


class ActionBoundaryGate:
    """Fail-closed readback of the authoritative Git queue immediately before action.

    The local SQLite queue is only a scheduler journal. This gate refreshes the
    remote ``chat`` branch, re-validates the approved protocol blobs, re-binds
    the source by ``source_path + source_blob_sha``, and then reads completion
    markers plus STATUS. A caller must run this gate before local/remote claim,
    agent wake, provider calls and external side effects.
    """

    def __init__(
        self,
        bare: Path,
        *,
        expected_protocol: Mapping[str, str],
        inbox: str = "chat/to-hermes/",
        completion_dir: str = "chat/completed/to-hermes/",
        status_path: str = "chat/STATUS.md",
    ) -> None:
        if not expected_protocol:
            raise ValueError("approved protocol blob hashes are required")
        if not inbox.startswith("chat/") or not inbox.endswith("/"):
            raise ValueError("inbox must be a chat/.../ prefix")
        if not completion_dir.startswith("chat/completed/") or not completion_dir.endswith("/"):
            raise ValueError("completion_dir must be a chat/completed/.../ prefix")
        self.bare = bare.resolve(strict=True)
        self.expected_protocol = dict(expected_protocol)
        self.inbox = inbox
        self.completion_dir = completion_dir
        self.status_path = status_path

    def _refresh_snapshot(self) -> str:
        _git(
            self.bare,
            "fetch",
            "--no-tags",
            "--depth=1",
            "origin",
            "+refs/heads/chat:refs/remotes/origin/chat",
        )
        snapshot = _git(self.bare, "rev-parse", "refs/remotes/origin/chat", max_stdout=256).decode().strip()
        allowed = {
            "chat/README.md",
            "chat/LEASE_PROTOCOL.md",
            "chat/RESOURCE_LEASE_PROTOCOL.md",
            "chat/QUEUE_BASELINE.md",
        }
        for path, expected in self.expected_protocol.items():
            if path not in allowed:
                raise RemoteStateError("unexpected protocol path in approval snapshot: " + path)
            actual = _git(self.bare, "rev-parse", snapshot + ":" + path, max_stdout=256).decode().strip()
            if actual != expected:
                raise RemoteStateError("protocol changed; review before action: " + path)
        return snapshot

    def _source(self, snapshot: str, source_path: str, source_blob_sha: str) -> tuple[str, bool | None, bool | None]:
        if not source_path.startswith(self.inbox) or not source_path.endswith(".md"):
            raise RemoteStateError("source path is outside the configured inbox")
        actual = _git(self.bare, "rev-parse", snapshot + ":" + source_path, max_stdout=256).decode().strip()
        if actual != source_blob_sha:
            raise RemoteStateError("source identity changed or disappeared; fail closed")
        text = _cat_blob(self.bare, actual, max_bytes=4 * 1024 * 1024).decode("utf-8")
        action_required = _parse_bool_metadata(text, "action_required")
        reply_required = _parse_bool_metadata(text, "reply_required")
        message_id = Path(source_path).stem + "--" + source_blob_sha
        return message_id, action_required, reply_required

    def _completion(self, snapshot: str, source_path: str, source_blob_sha: str,
                    source_message_id: str) -> tuple[str, str, str] | None:
        raw = _git(self.bare, "ls-tree", "-rz", "-r", snapshot, "--", self.completion_dir)
        matches: list[tuple[str, str, str]] = []
        for record in raw.split(b"\0"):
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, sha = meta.decode("ascii").split()
            path = raw_path.decode("utf-8")
            if kind != "blob" or not path.endswith(".json"):
                continue
            if mode not in ("100644", "100755"):
                raise RemoteStateError("non-regular completion marker refused: " + path)
            try:
                body = json.loads(_cat_blob(self.bare, sha, max_bytes=1024 * 1024))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RemoteStateError("unparseable completion marker: " + path) from exc
            if not isinstance(body, dict):
                raise RemoteStateError("completion marker is not an object: " + path)
            marker_id = body.get("message_id")
            marker_path = _normalize_path(str(body.get("message_path", "")))
            marker_blob = str(body.get("message_blob_sha", ""))
            id_match = marker_id == source_message_id
            pair_match = marker_path == source_path and marker_blob == source_blob_sha
            if not (id_match or pair_match):
                continue
            if marker_blob and marker_blob != source_blob_sha:
                raise RemoteStateError("completion identity conflicts with source blob: " + path)
            if marker_path and marker_path != source_path:
                raise RemoteStateError("completion identity conflicts with source path: " + path)
            status = str(body.get("status", ""))
            if status not in TERMINAL_COMPLETION_STATUSES:
                raise RemoteStateError("matching completion has non-terminal/unknown status: " + path)
            matches.append((path, sha, status))
        if not matches:
            return None
        statuses = {item[2] for item in matches}
        if len(statuses) != 1:
            raise RemoteStateError("conflicting completion markers for one source identity")
        matches.sort(key=lambda item: item[0])
        return matches[-1]

    def _latest_status(self, snapshot: str, source_path: str, source_blob_sha: str) -> tuple[str, str] | None:
        sha = _git(self.bare, "rev-parse", snapshot + ":" + self.status_path, max_stdout=256).decode().strip()
        text = _cat_blob(self.bare, sha, max_bytes=8 * 1024 * 1024).decode("utf-8")
        latest: tuple[str, str] | None = None
        for line in text.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 7:
                continue
            path = _status_path(cells[3])
            if path != source_path:
                continue
            blob = _status_blob(cells[4])
            if blob is None or not source_blob_sha.startswith(blob):
                continue
            kind = _status_kind(cells[5])
            if kind is not None:
                latest = (kind, line)
        return latest

    def inspect(self, source_path: str, source_blob_sha: str) -> GateDecision:
        if not re.fullmatch(r"[0-9a-f]{40}", source_blob_sha):
            raise ValueError("source_blob_sha must be a full Git SHA-1")
        with (self.bare / "token-action-gate.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            snapshot = self._refresh_snapshot()
            message_id, action_required, reply_required = self._source(
                snapshot, source_path, source_blob_sha
            )
            completion = self._completion(snapshot, source_path, source_blob_sha, message_id)
            status_row = self._latest_status(snapshot, source_path, source_blob_sha)
            checked_at = _now_utc8()

            if completion is not None:
                path, blob, completion_status = completion
                return GateDecision(
                    "REMOTE_COMPLETED",
                    checked_at,
                    snapshot,
                    source_path,
                    source_blob_sha,
                    message_id,
                    action_required,
                    reply_required,
                    completion_path=path,
                    completion_blob_sha=blob,
                    completion_status=completion_status,
                    status_row=status_row[1] if status_row else None,
                )

            if action_required is False:
                return GateDecision(
                    "NON_REQUEST",
                    checked_at,
                    snapshot,
                    source_path,
                    source_blob_sha,
                    message_id,
                    action_required,
                    reply_required,
                    status_row=status_row[1] if status_row else None,
                )

            if status_row is not None and status_row[0] in TERMINAL_COMPLETION_STATUSES:
                raise RemoteStateError(
                    "terminal STATUS exists without a matching completion for an actionable/unknown source; "
                    "cannot distinguish legitimate crash-recovery state from premature close"
                )

            return GateDecision(
                "ACTIONABLE",
                checked_at,
                snapshot,
                source_path,
                source_blob_sha,
                message_id,
                action_required,
                reply_required,
                status_row=status_row[1] if status_row else None,
            )
