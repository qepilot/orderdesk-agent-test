"""Module 3: context engineering. Deciding what the model sees on each call.

The conversation history (messages) is the record. What is sent to the model is a view of it.
Keeping the two apart means the trace stays complete while the prompt stays small.

Four levers, cheapest first:
  1. Prevent   tools return less: ranges instead of files, aggregates instead of rows (assistant/tools.py).
  2. Clip      one oversized result is cut with a visible marker (assistant/guards.clip, used by the harness).
  3. Clear     old tool results are replaced by a one-line stub once the context passes a budget (here).
  4. Persist   what matters is written to notes that are re-shown after clearing (assistant/state.py).
A fifth, summarising old turns with a model call, is shown in the Module 3 notebook.
"""

from __future__ import annotations

import json


def estimate_tokens(text: str) -> int:
    """A rough count: about four characters per token for English text and code.

    Good enough to decide when to act. For billing, trust the usage numbers the API returns.
    """
    return (len(text) + 3) // 4


def message_tokens(message: dict) -> int:
    size = estimate_tokens(str(message.get("content") or ""))
    for call in message.get("tool_calls") or []:
        size += estimate_tokens(call["function"]["name"] + call["function"]["arguments"])
    return size + 4      # a few tokens of framing per message


def conversation_tokens(messages: list[dict]) -> int:
    return sum(message_tokens(message) for message in messages)


class ContextManager:
    """Builds the view of the history that is sent to the model.

    While the estimated size is under max_tokens the view is the history itself. Above it, the
    oldest tool results are replaced by stubs, keeping the newest keep_recent results intact,
    and the investigation notes (if any) are appended to the system prompt so nothing important
    depends on the cleared text.
    """

    def __init__(self, max_tokens: int = 12_000, keep_recent: int = 3, state=None, min_chars: int = 400):
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self.min_chars = min_chars        # results smaller than this are never worth clearing
        self.state = state
        self.history: list[dict] = []     # one entry per prepare(): sizes before and after

    def prepare(self, messages: list[dict]) -> list[dict]:
        before = conversation_tokens(messages)
        if before <= self.max_tokens:
            self.history.append({"before": before, "after": before, "cleared": 0})
            return messages

        calls = {call["id"]: call["function"] for message in messages for call in message.get("tool_calls") or []}
        tool_positions = [index for index, message in enumerate(messages) if message["role"] == "tool"]
        clearable = tool_positions[:-self.keep_recent] if self.keep_recent else tool_positions
        view, size, cleared = list(messages), before, 0
        for index in clearable:
            if size <= self.max_tokens:
                break
            message = messages[index]
            if len(str(message["content"])) < self.min_chars:
                continue                  # a stub would be no shorter than a small result
            function = calls.get(message["tool_call_id"], {"name": "tool", "arguments": "{}"})
            stub = (f"[cleared to save context: {function['name']}({_brief(function['arguments'])}) returned "
                    f"{len(str(message['content']))} characters. Call it again if you need the raw result.]")
            view[index] = {**message, "content": stub}
            size -= message_tokens(message) - message_tokens(view[index])
            cleared += 1
        if cleared and self.state is not None and view and view[0]["role"] == "system":
            view[0] = {**view[0], "content": view[0]["content"] + "\n\n" + self.state.render()}
            size = conversation_tokens(view)
        self.history.append({"before": before, "after": size, "cleared": cleared})
        return view


def _brief(arguments: str, limit: int = 60) -> str:
    try:
        text = ", ".join(f"{key}={value!r}" for key, value in json.loads(arguments).items())
    except (ValueError, AttributeError):
        text = arguments
    return text if len(text) <= limit else text[: limit - 3] + "..."
