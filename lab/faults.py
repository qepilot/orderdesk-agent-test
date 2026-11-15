"""Fault injection for Module 5: make a model or a tool fail on purpose, a known number of times."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from assistant.guards import ToolError
from assistant.llm import ModelError, Reply
from assistant.tools import Tool


class FlakyModel:
    """Wraps a model and raises ModelError for the first `fail_first` calls."""

    def __init__(self, inner: Any, fail_first: int = 1, kind: str = "unavailable"):
        self.inner, self.remaining, self.kind = inner, fail_first, kind
        self.name = f"flaky({inner.name})"

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        if self.remaining > 0:
            self.remaining -= 1
            raise ModelError(self.kind, "injected failure: the endpoint returned HTTP 503")
        return self.inner.complete(messages, tools, **options)


def flaky_tool(tool: Tool, fail_first: int = 2, kind: str = "timeout") -> Tool:
    """A copy of the tool whose first `fail_first` calls fail with a transient error."""
    state = {"remaining": fail_first, "calls": 0}

    def fn(**arguments):
        state["calls"] += 1
        if state["remaining"] > 0:
            state["remaining"] -= 1
            raise ToolError(kind, f"injected failure: {tool.name} did not answer in time")
        return tool.fn(**arguments)

    wrapped = replace(tool, fn=fn)
    wrapped.fault_state = state          # so a lab can show how often it was really called
    return wrapped


def broken_tool(tool: Tool) -> Tool:
    """A copy of the tool that always raises an unexpected exception (a bug, not a refusal)."""
    def fn(**arguments):
        raise ConnectionResetError("injected failure: connection reset by peer")
    return replace(tool, fn=fn)
