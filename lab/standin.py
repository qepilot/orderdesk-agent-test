"""A stand-in for the model, so that every lab runs with no API key and gives the same result twice.

ScriptedModel plays back a list of turns written by hand (lab/scripts.py). Each turn is some text
and zero or more tool calls. The harness cannot tell the difference: it validates, executes,
records and limits the scripted calls exactly as it would a real model's. So everything about the
harness is real; only the judgement ("which tool next?", "what does this mean?") is canned.

Two things make it more than a tape recorder:
  - it skips tool calls for tools it was not offered, so one script works with small and large tool sets;
  - it reads the calls_done list of a saved investigation state and skips those calls, the way a
    real model reads its notes after an interruption.

Scripted models are also how you test a harness: write a script in which the "model" misbehaves
(lab/scripts.py has several) and check that the harness holds.
"""

from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from typing import Any

from assistant.context import conversation_tokens, estimate_tokens
from assistant.llm import Reply, ToolCall, Usage, parse_tool_calls

_CALLS_DONE = re.compile(r"^calls_done: (\[.*\])\s*$", re.MULTILINE)
_SIGNATURE = re.compile(r"^(\w+)\((.*)\)$", re.DOTALL)
ALWAYS_REPLAY = {"submit_findings"}


class ScriptedModel:
    def __init__(self, turns: list[dict], name: str = "scripted-stand-in"):
        self.name = name
        self.turns = deepcopy(turns)
        self.cursor = 0

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        offered = {tool["function"]["name"] for tool in tools or []}
        done = _calls_done(messages)
        saved_state = "\n".join(str(m.get("content") or "") for m in messages
                                if m["role"] == "user" and "<investigation_state>" in str(m.get("content") or ""))
        prompt_tokens = conversation_tokens(messages) + estimate_tokens(json.dumps(tools or []))
        while self.cursor < len(self.turns):
            turn = self.turns[self.cursor]
            self.cursor += 1
            scripted = turn.get("calls", [])
            calls = [call for call in scripted
                     if (not offered or call["name"] in offered or call.get("force")) and not _already_done(call, done, saved_state)]
            if scripted and not calls:
                continue                      # nothing left to do in this turn: move on
            return self._reply(turn.get("say", ""), [_only_citable(call, offered) for call in calls], prompt_tokens)
        return self._reply("(the script has no more turns)", [], prompt_tokens)

    @staticmethod
    def _reply(text: str, calls: list[dict], prompt_tokens: int) -> Reply:
        raw = [{"id": f"call_{uuid.uuid4().hex[:10]}", "type": "function",
                "function": {"name": call["name"],
                             "arguments": call.get("arguments_raw") or json.dumps(call.get("args", {}))}}
               for call in calls]
        tool_calls: list[ToolCall] = parse_tool_calls(raw)
        output_tokens = estimate_tokens(text + "".join(call.arguments for call in tool_calls))
        return Reply(content=text, tool_calls=tool_calls, finish_reason="tool_calls" if tool_calls else "stop",
                     usage=Usage(prompt_tokens, output_tokens), model="scripted-stand-in")


def _only_citable(call: dict, offered: set[str]) -> dict:
    """In a final answer, keeps only the evidence the stand-in could have looked up with the tools it had."""
    evidence = call.get("args", {}).get("evidence")
    if not evidence:
        return call
    kept = [{key: value for key, value in item.items() if key != "_needs"} for item in evidence
            if not item.get("_needs") or not offered or item["_needs"] in offered]
    return {**call, "args": {**call["args"], "evidence": kept}}


def _calls_done(messages: list[dict]) -> list[tuple[str, dict]]:
    done = []
    for message in messages:
        for found in _CALLS_DONE.findall(str(message.get("content") or "")):
            for signature in json.loads(found):
                match = _SIGNATURE.match(signature)
                if match:
                    done.append((match.group(1), json.loads(match.group(2))))
    return done


def _already_done(call: dict, done: list[tuple[str, dict]], saved_state: str = "") -> bool:
    if call["name"] in ALWAYS_REPLAY or "arguments_raw" in call:
        return False
    wanted = call.get("args", {})
    if saved_state and call["name"] == "record_note":                # the note is already in the saved state
        return wanted.get("note", "") in saved_state
    if saved_state and call["name"] == "update_plan":                # the saved plan is at least this far along
        return saved_state.count("[x]") >= sum(step["status"] == "done" for step in wanted.get("steps", []))
    return any(name == call["name"] and all(args.get(key) == value for key, value in wanted.items())
               for name, args in done)


class CannedModel:
    """Module 1 stand-in: returns hand-written sample answers, one per call, with no tools involved."""

    def __init__(self, answers: list[str], name: str = "canned-samples"):
        self.name = name
        self.answers = list(answers)
        self.cursor = 0

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        answer = self.answers[min(self.cursor, len(self.answers) - 1)]
        self.cursor += 1
        return Reply(content=answer, usage=Usage(conversation_tokens(messages), estimate_tokens(answer)),
                     model=self.name)
