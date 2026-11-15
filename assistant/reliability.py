"""Module 5: failure handling that belongs in code rather than in the model's turns.

When a tool fails for a transient reason, asking the model what to do costs a full model call
and it will almost always say "try again". with_retries does that in code. Failures that need
judgement (a refusal, a wrong argument, a missing table) still go back to the model as data.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from .guards import ToolError
from .llm import ModelError, Reply
from .tools import Tool

TRANSIENT_KINDS = frozenset({"timeout", "unavailable", "rate_limited"})


def with_retries(tool: Tool, attempts: int = 3, base_delay: float = 0.2,
                 retry_kinds: frozenset[str] = TRANSIENT_KINDS, sleep=time.sleep) -> Tool:
    """A copy of the tool that retries transient failures with exponential backoff before giving up.

    Only safe for tools that can be repeated without harm (reads). Never wrap a write this way
    unless the write is idempotent.
    """
    if tool.risk != "read":
        raise ValueError(f"{tool.name} is a write tool; retrying it automatically could repeat a side effect")

    def fn(**arguments):
        for attempt in range(1, attempts + 1):
            try:
                return tool.fn(**arguments)
            except ToolError as error:
                if error.kind not in retry_kinds or attempt == attempts:
                    raise
                sleep(base_delay * 2 ** (attempt - 1))

    return replace(tool, fn=fn)


class FallbackModel:
    """Tries the primary model; when it is unavailable, answers with the secondary one."""

    def __init__(self, primary: Any, secondary: Any):
        self.primary, self.secondary = primary, secondary
        self.name = f"{primary.name} (fallback: {secondary.name})"
        self.fallbacks = 0

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        try:
            return self.primary.complete(messages, tools, **options)
        except ModelError as error:
            if error.kind not in ("unavailable", "bad_response"):
                raise                      # a wrong key or a bad request fails on any model
            self.fallbacks += 1
            return self.secondary.complete(messages, tools, **options)
