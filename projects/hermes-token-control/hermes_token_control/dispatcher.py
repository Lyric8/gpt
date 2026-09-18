from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .queue import EventQueue
from .remote_gate import ActionBoundaryGate, GateDecision, RemoteStateError, TERMINAL_GATE_STATUSES


BOUNDARIES = frozenset({"remote-message-claim", "wake-agent", "model-request", "business-write"})


@dataclass(frozen=True)
class DispatchTicket:
    event_id: str
    owner: str
    epoch: int
    expires: float
    source_path: str
    source_blob_sha: str
    source_message_id: str
    preclaim_snapshot: str
    postclaim_snapshot: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoundaryPermit:
    boundary: str
    event_id: str
    owner: str
    epoch: int
    checked_at: str
    snapshot_commit: str
    source_path: str
    source_blob_sha: str
    source_message_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActionDispatcher:
    """Zero-model dispatcher gate for the durable local source queue.

    This class does not grant Git message/resource ownership. It only guarantees
    that authoritative completion/STATUS state is re-read before a local event
    can proceed toward a remote claim, agent wake, model request, or business
    write. The host adapter must separately acquire and revalidate current Git
    message/resource leases and fencing tokens.
    """

    def __init__(
        self,
        bare: Path,
        queue: EventQueue,
        *,
        expected_protocol: Mapping[str, str],
        owner: str,
        channel: str = "github:Lyric8/gpt:chat:to-hermes",
        inbox: str = "chat/to-hermes/",
        completion_dir: str = "chat/completed/to-hermes/",
        local_ttl: float = 120,
        max_attempts: int = 5,
        gate_retry_delay: float = 15,
    ) -> None:
        if not owner.strip():
            raise ValueError("dispatcher owner is required")
        if not 0 < local_ttl <= 3600 or max_attempts <= 0 or gate_retry_delay < 0:
            raise ValueError("invalid dispatcher lease/retry policy")
        self.queue = queue
        self.owner = owner
        self.channel = channel
        self.local_ttl = local_ttl
        self.max_attempts = max_attempts
        self.gate_retry_delay = gate_retry_delay
        self.gate = ActionBoundaryGate(
            bare,
            expected_protocol=expected_protocol,
            inbox=inbox,
            completion_dir=completion_dir,
        )

    @staticmethod
    def _identity(event: Mapping[str, Any]) -> tuple[str, str]:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("event payload missing")
        path = payload.get("key")
        version = payload.get("version")
        if path != event.get("item_key") or version != event.get("version"):
            raise ValueError("queue row and immutable payload identity disagree")
        if not isinstance(path, str) or not isinstance(version, str):
            raise ValueError("event source identity missing")
        return path, version

    @staticmethod
    def _terminal_state(decision: GateDecision) -> str:
        if decision.status == "REMOTE_COMPLETED":
            return "REMOTE_COMPLETED"
        if decision.status == "NON_REQUEST":
            return "NON_REQUEST"
        raise ValueError("decision is not terminal")

    @staticmethod
    def _evidence(decision: GateDecision, boundary: str) -> dict[str, Any]:
        evidence = decision.as_dict()
        evidence["boundary"] = boundary
        evidence["gate"] = "authoritative-git-readback"
        return evidence

    def claim_next_actionable(self, *, max_scan: int = 64) -> DispatchTicket | None:
        if max_scan <= 0:
            raise ValueError("max_scan must be positive")
        for _ in range(max_scan):
            candidate = self.queue.peek_due(channel=self.channel, max_attempts=self.max_attempts)
            if candidate is None:
                return None
            source_path, source_blob = self._identity(candidate)
            pre = self.gate.inspect(source_path, source_blob)
            if pre.status in TERMINAL_GATE_STATUSES:
                self.queue.reconcile_remote(
                    candidate["id"], source_blob,
                    state=self._terminal_state(pre),
                    evidence=self._evidence(pre, "local-claim"),
                )
                continue
            if pre.status != "ACTIONABLE":
                raise RemoteStateError("unknown gate status before local claim: " + pre.status)

            claimed = self.queue.claim_specific(
                candidate["id"], self.owner, source_blob,
                ttl=self.local_ttl, max_attempts=self.max_attempts,
            )
            if claimed is None:
                continue
            try:
                post = self.gate.inspect(source_path, source_blob)
            except Exception as exc:
                self.queue.release_claim(
                    claimed["id"], self.owner, claimed["epoch"],
                    delay=self.gate_retry_delay,
                    reason="post-claim readback failed: " + str(exc),
                    refund_attempt=True,
                )
                raise
            if post.status in TERMINAL_GATE_STATUSES:
                self.queue.reconcile_owned_remote(
                    claimed["id"], self.owner, claimed["epoch"],
                    state=self._terminal_state(post),
                    evidence=self._evidence(post, "local-claim-postcheck"),
                )
                continue
            if post.status != "ACTIONABLE":
                self.queue.release_claim(
                    claimed["id"], self.owner, claimed["epoch"],
                    delay=self.gate_retry_delay,
                    reason="unknown post-claim gate status: " + post.status,
                    refund_attempt=True,
                )
                raise RemoteStateError("unknown gate status after local claim: " + post.status)
            return DispatchTicket(
                event_id=claimed["id"], owner=self.owner, epoch=claimed["epoch"],
                expires=claimed["expires"], source_path=source_path,
                source_blob_sha=source_blob, source_message_id=post.source_message_id,
                preclaim_snapshot=pre.snapshot_commit, postclaim_snapshot=post.snapshot_commit,
            )
        raise RuntimeError("dispatcher exceeded bounded reconciliation scan")

    def ticket_for_owned(self, event_id: str, epoch: int) -> DispatchTicket:
        row = self.queue.owned_event(event_id, self.owner, epoch)
        source_path, source_blob = self._identity(row)
        return DispatchTicket(
            event_id=event_id, owner=self.owner, epoch=epoch, expires=row["expires"],
            source_path=source_path, source_blob_sha=source_blob,
            source_message_id=Path(source_path).stem + "--" + source_blob,
            preclaim_snapshot="unknown", postclaim_snapshot="unknown",
        )

    def permit(self, ticket: DispatchTicket, boundary: str) -> BoundaryPermit | None:
        """Return a fresh readback permit, or ``None`` if remote state is terminal."""
        if boundary not in BOUNDARIES:
            raise ValueError("unsupported action boundary")
        if ticket.owner != self.owner:
            raise ValueError("ticket owner does not match dispatcher")
        row = self.queue.owned_event(ticket.event_id, ticket.owner, ticket.epoch)
        source_path, source_blob = self._identity(row)
        if source_path != ticket.source_path or source_blob != ticket.source_blob_sha:
            raise ValueError("ticket identity no longer matches local queue row")
        try:
            decision = self.gate.inspect(source_path, source_blob)
        except Exception as exc:
            self.queue.release_claim(
                ticket.event_id, ticket.owner, ticket.epoch,
                delay=self.gate_retry_delay,
                reason=f"{boundary} readback failed: {exc}", refund_attempt=True,
            )
            raise
        if decision.status in TERMINAL_GATE_STATUSES:
            self.queue.reconcile_owned_remote(
                ticket.event_id, ticket.owner, ticket.epoch,
                state=self._terminal_state(decision),
                evidence=self._evidence(decision, boundary),
            )
            return None
        if decision.status != "ACTIONABLE":
            self.queue.release_claim(
                ticket.event_id, ticket.owner, ticket.epoch,
                delay=self.gate_retry_delay,
                reason=f"unknown {boundary} gate status: {decision.status}", refund_attempt=True,
            )
            raise RemoteStateError("unknown gate status at action boundary: " + decision.status)
        return BoundaryPermit(
            boundary=boundary, event_id=ticket.event_id, owner=ticket.owner,
            epoch=ticket.epoch, checked_at=decision.checked_at,
            snapshot_commit=decision.snapshot_commit, source_path=source_path,
            source_blob_sha=source_blob, source_message_id=decision.source_message_id,
        )
