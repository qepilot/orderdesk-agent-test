"""Module 5: observability. Every model call, tool call, approval and stop becomes one event.

An event is a dict with a timestamp, a run id and a type. Events are kept in memory and, when a
path is given, appended to a JSONL file (one JSON object per line), which any log tool can read.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path


class Tracer:
    def __init__(self, path: str | Path | None = None, *, run_id: str | None = None, echo: bool = False,
                 keep_outputs: bool = True):
        self.run_id = run_id or uuid.uuid4().hex[:10]
        self.path = Path(path) if path else None
        self.echo = echo
        self.keep_outputs = keep_outputs
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **data) -> None:
        if not self.keep_outputs and "output" in data:
            data = {**data, "output": f"<{len(data['output'])} chars not stored>"}
        entry = {"ts": round(time.time(), 3), "run_id": self.run_id, "event": event, **data}
        self.events.append(entry)
        if self.path:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, default=str) + "\n")
        if self.echo:
            print(format_event(entry))


def load_trace(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def format_event(event: dict) -> str:
    kind = event["event"]
    if kind == "model_call":
        calls = ", ".join(call["name"] for call in event["tool_calls"]) or "no tool calls"
        text = f' "{event["text"][:90]}"' if event.get("text") else ""
        return (f"step {event['step']:>2}  MODEL  {event['input_tokens']:>6} in / {event['output_tokens']:>4} out  "
                f"-> {calls}{text}")
    if kind == "tool_call":
        mark = "ok " if event["ok"] else "ERR"
        args = json.dumps(event["args"])
        return (f"         TOOL   {mark} {event['name']}({args if len(args) < 90 else args[:87] + '...'}) "
                f"-> {event['chars']} chars" + ("" if event["ok"] else f"  [{event['kind']}]"))
    if kind == "approval":
        return f"         HUMAN  {'approved' if event['approved'] else 'refused '} {event['name']} ({event['reason']})"
    if kind == "run_end":
        return (f"END      {event['status']} ({event['stop_reason']}): {event['steps']} steps, {event['tool_calls']} "
                f"tool calls, {event['input_tokens']} in / {event['output_tokens']} out tokens, {event['seconds']} s")
    if kind == "run_start":
        return f"START    model={event['model']} tools={len(event['tools'])} task={event['task'][:80]!r}"
    return f"         {kind.upper()} {json.dumps({k: v for k, v in event.items() if k not in ('ts', 'run_id', 'event')})[:160]}"


def print_trace(events: list[dict]) -> None:
    for event in events:
        print(format_event(event))


def price_per_million() -> tuple[float, float]:
    """Prices come from the environment because they differ per model and change often."""
    return float(os.getenv("PRICE_INPUT_PER_MTOK", "0") or 0), float(os.getenv("PRICE_OUTPUT_PER_MTOK", "0") or 0)


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = price_per_million()
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def summarize(events: list[dict]) -> dict:
    """The numbers you would put on a dashboard, computed from one run's events."""
    model_calls = [event for event in events if event["event"] == "model_call"]
    tool_calls = [event for event in events if event["event"] == "tool_call"]
    end = next((event for event in reversed(events) if event["event"] == "run_end"), {})
    input_tokens = sum(event["input_tokens"] for event in model_calls)
    output_tokens = sum(event["output_tokens"] for event in model_calls)
    return {
        "status": end.get("status", "unknown"),
        "stop_reason": end.get("stop_reason", "unknown"),
        "steps": len(model_calls),
        "tool_calls": len(tool_calls),
        "tools_used": dict(Counter(event["name"] for event in tool_calls)),
        "tool_errors": dict(Counter(event["kind"] for event in tool_calls if not event["ok"])),
        "approvals_refused": sum(1 for event in events if event["event"] == "approval" and not event["approved"]),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "largest_prompt_tokens": max((event["input_tokens"] for event in model_calls), default=0),
        "model_seconds": round(sum(event["seconds"] for event in model_calls), 2),
        "tool_seconds": round(sum(event["seconds"] for event in tool_calls), 2),
        "seconds": end.get("seconds", 0),
        "cost_usd": round(cost_usd(input_tokens, output_tokens), 4),
    }
