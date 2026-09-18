from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Stage1Policy:
    """Non-blocking Stage-1 policy.

    These are advisory/compaction thresholds, not admission gates. The only
    hard limit left in the send path is the provider/model's real protocol
    limit. Budget pressure changes how work is represented and segmented; it
    never rejects the owner's interactive request solely for cost/token budget.
    """

    compact_at_tokens: int = 48_000
    strong_alert_at_tokens: int = 64_000
    target_provider_calls_per_segment: int = 6
    strong_alert_provider_calls_per_segment: int = 12
    gross_target_tokens: int = 95_059_623

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(type(v) is not int or v <= 0 for v in values.values()):
            raise ValueError("stage1 policy values must be positive integers")
        if self.strong_alert_at_tokens < self.compact_at_tokens:
            raise ValueError("strong token alert must not precede compaction threshold")
        if self.strong_alert_provider_calls_per_segment < self.target_provider_calls_per_segment:
            raise ValueError("strong call alert must not precede target")


@dataclass(frozen=True)
class Advisory:
    allow_task: bool
    request_action: str
    severity: str
    reasons: tuple[str, ...]
    metrics: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "allow_task": self.allow_task,
            "request_action": self.request_action,
            "severity": self.severity,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def advise(*, input_tokens: int, provider_calls_in_segment: int,
           period_gross_tokens: int = 0, policy: Stage1Policy = Stage1Policy()) -> Advisory:
    """Return a non-blocking action plan; never a budget rejection.

    request_action applies to representation of the *next physical request*:
      SEND      - current representation is below the compaction threshold.
      COMPACT   - persist evidence, replace large results with manifests/hashes,
                  remove only checkpoint-covered complete turns, then recount.
      SEGMENT   - do the same compaction and split source work before sending.

    allow_task is intentionally always True. A caller must still respect real
    provider context/protocol limits and data-integrity failures.
    """

    metrics = {
        "input_tokens": input_tokens,
        "provider_calls_in_segment": provider_calls_in_segment,
        "period_gross_tokens": period_gross_tokens,
    }
    if any(type(v) is not int or v < 0 for v in metrics.values()):
        raise ValueError("stage1 metrics must be nonnegative integers")

    reasons: list[str] = []
    severity = "ok"
    action = "SEND"

    if input_tokens >= policy.strong_alert_at_tokens:
        action = "SEGMENT"
        severity = "strong"
        reasons.append("request context crossed strong advisory threshold")
    elif input_tokens >= policy.compact_at_tokens:
        action = "COMPACT"
        severity = "warning"
        reasons.append("request context crossed compaction threshold")

    if provider_calls_in_segment > policy.strong_alert_provider_calls_per_segment:
        severity = "strong"
        reasons.append("provider-call count crossed strong advisory threshold")
    elif provider_calls_in_segment > policy.target_provider_calls_per_segment:
        if severity == "ok":
            severity = "warning"
        reasons.append("provider-call count is above the stage1 batching target")

    if period_gross_tokens > policy.gross_target_tokens:
        if severity == "ok":
            severity = "warning"
        reasons.append("matched-work gross-token target is currently exceeded")

    return Advisory(True, action, severity, tuple(reasons), metrics)


def alert_payload(*, task_id: str, advisory: Advisory, evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Build a sender-ready payload without knowing or storing sender credentials."""
    if not task_id.strip():
        raise ValueError("task_id is required")
    return {
        "kind": "token-control.stage1-advisory",
        "task_id": task_id,
        "blocking": False,
        "advisory": advisory.as_dict(),
        "evidence": dict(evidence),
    }
