"""Module 3: investigation state. What the agent knows that must outlive the context window.

Three kinds of memory, kept apart on purpose:

  conversation context   the messages sent to the model. Lost when cleared; gone when the process ends.
  execution state        this file: plan, facts, open questions, what was already inspected. Saved to
                         disk after every tool call, so an interrupted run can be resumed.
  long-term memory       lessons kept across investigations (assistant/memory.py, optional extension).

The model writes the plan and the notes through tools. The list of what was inspected is written
by code from the ledger, because a model's own account of what it did is not a reliable record.
The raw tool results are kept too (evidence_log): after a restart the final answer may still quote
evidence gathered before the interruption, and the quote check must be able to find it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MARKS = {"done": "[x]", "in_progress": "[>]", "pending": "[ ]", "dropped": "[-]"}
BOOKKEEPING_TOOLS = {"update_plan", "record_note", "submit_findings", "load_skill"}   # not evidence


@dataclass
class InvestigationState:
    task: str = ""
    plan: list[dict] = field(default_factory=list)              # {"step", "status"}
    facts: list[dict] = field(default_factory=list)             # {"text", "ref"}
    open_questions: list[dict] = field(default_factory=list)
    files_read: dict[str, list[str]] = field(default_factory=dict)
    queries_run: list[str] = field(default_factory=list)
    documents_read: list[str] = field(default_factory=list)
    calls_done: list[str] = field(default_factory=list)         # signatures of successful tool calls
    evidence_log: list[str] = field(default_factory=list)       # every successful tool result, for the quote check
    status: str = "in_progress"
    stop_reason: str = ""
    path: str = ""                                              # where to save after every observation

    # -- written by code ---------------------------------------------------------------------

    def observe(self, record) -> None:
        """Called by the harness after every tool call."""
        if record.ok and record.name not in BOOKKEEPING_TOOLS:
            if record.signature not in self.calls_done:
                self.calls_done.append(record.signature)
            self.evidence_log.append(record.output)
            args = record.args or {}
            if record.name == "read_file":
                span = f"{args.get('start_line', 1)}-{args.get('end_line') or 'end'}"
                self.files_read.setdefault(args.get("path", "?"), []).append(span)
            elif record.name in ("run_sql", "explain_query"):
                self.queries_run.append(" ".join(str(args.get("query", "")).split())[:200])
            elif record.name == "read_knowledge":
                self.documents_read.append(args.get("doc_id", "?"))
        if self.path:
            self.save(self.path)

    # -- shown to the model ---------------------------------------------------------------------

    def render(self) -> str:
        lines = ["<investigation_state>", f"Task: {self.task}"]
        if self.plan:
            lines.append("Plan:")
            lines += [f"  {MARKS.get(step['status'], '[ ]')} {step['step']}" for step in self.plan]
        if self.facts:
            lines.append("Facts established:")
            lines += [f"  - {fact['text']}" + (f" ({fact['ref']})" if fact.get("ref") else "") for fact in self.facts]
        if self.open_questions:
            lines.append("Open questions:")
            lines += [f"  - {question['text']}" for question in self.open_questions]
        lines.append("Evidence-gathering calls already made (their results are stored; repeat one only if you need "
                     "the raw text again):")
        lines.append("calls_done: " + json.dumps(self.calls_done))
        lines.append("</investigation_state>")
        return "\n".join(lines)

    def resume_prompt(self) -> str:
        """The first user message of a resumed run: the task plus everything worth knowing from before."""
        return (f"{self.task}\n\nYou started this investigation earlier and were interrupted. Your saved state is "
                "below. Do not repeat calls listed under calls_done unless you need the raw result again; continue "
                "with the next open step of the plan and finish with submit_findings.\n\n" + self.render())

    # -- persistence -----------------------------------------------------------------------------

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)       # atomic: a crash never leaves half a file
        return path

    @classmethod
    def load(cls, path: str | Path) -> "InvestigationState":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))
