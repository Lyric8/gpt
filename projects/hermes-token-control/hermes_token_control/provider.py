from __future__ import annotations

from typing import Any, Callable

from .context import validate_messages
from .governor import Governor, IntegrityError, TokenCount, Usage


class GuardedChatCompletions:
    """Explicit sync/non-streaming OpenAI-compatible transport integration.

    This is NOT an auto-installed Hermes plugin. Install at the actual provider
    send site. The SDK must expose max_retries=0; transport-level replay must
    also be off. Streaming/Anthropic/Responses paths require their own adapters
    and must NOT be routed around this gate. No exception is auto-retried here.
    """
    def __init__(self, client: Any, governor: Governor,
                 counter: Callable[[dict[str, Any]], TokenCount], *, context_window: int):
        if getattr(client, "max_retries", None) != 0:
            raise IntegrityError("SDK max_retries must be explicitly zero")
        if type(context_window) is not int or context_window <= 0:
            raise ValueError("verified model context window required")
        self.client, self.governor, self.counter = client, governor, counter
        self.context_window = context_window

    def create(self, *, task: str, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            raise IntegrityError("streaming adapter not certified; no bypass")
        if kwargs.get("n", 1) != 1:
            raise IntegrityError("multiple choices require different output reservation accounting")
        if "max_tokens" in kwargs and "max_completion_tokens" in kwargs:
            raise IntegrityError("ambiguous output limit")
        maximum = kwargs.get("max_completion_tokens", kwargs.get("max_tokens"))
        if type(maximum) is not int or maximum <= 0:
            raise IntegrityError("explicit provider output cap required")
        if kwargs.get("extra_body"):
            raise IntegrityError("extra_body overrides require a provider-specific reviewed adapter")
        validate_messages(kwargs.get("messages", []))
        # The counter receives the COMPLETE final payload, including schemas.
        counted = self.counter(kwargs)
        if counted.tokens + maximum > self.context_window:
            raise IntegrityError("input plus output reserve exceeds verified model context window")
        attempt = self.governor.admit(task, kwargs, counted, maximum)
        try:
            response = self.client.chat.completions.create(**kwargs)
        except BaseException as exc:
            # Persist an error type only, avoiding accidental credential/URL leakage.
            self.governor.settle(attempt, None, error=type(exc).__name__)
            raise
        try:
            raw = getattr(response, "usage", None)
            if raw is None:
                usage = None
            else:
                if hasattr(raw, "model_dump"):
                    raw = raw.model_dump()
                usage = Usage.from_chat_completions(raw)
        except (ValueError, TypeError, AttributeError) as exc:
            self.governor.settle(attempt, None, error="USAGE_PARSE_" + type(exc).__name__)
            raise IntegrityError("response received but usage could not be normalized") from exc
        self.governor.settle(attempt, usage)
        for choice in getattr(response, "choices", ()) or ():
            if getattr(choice, "finish_reason", None) in ("length", "content_filter"):
                raise IntegrityError("incomplete/filtered generation: do not execute or mark work complete")
        return response
