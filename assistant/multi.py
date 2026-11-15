"""Optional extension: several specialist agents on one task, and how to compare them with one agent.

Two patterns:

  review_with_specialists   code runs one agent per role on the same pull request, then merges the
                            findings. The orchestration is ordinary Python: no model decides who works.
  specialist_tool           a lead agent gets a tool that hands a question to a specialist agent and
                            receives only its short answer. The specialist's long tool results stay in
                            its own context (context isolation), which is the main technical reason to
                            use sub-agents at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from .harness import RunResult
from .tools import Tool

SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2}
_WORD = re.compile(r"[a-z0-9_]+")
_FILLER = frozenset("the a an of in to and or is are not no still with without for on does do".split())


def _key_words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _FILLER and len(word) > 2}


def same_problem(left: dict, right: dict, threshold: float = 0.5) -> bool:
    """A cheap duplicate test: do the two titles share most of their meaningful words?"""
    a, b = _key_words(left.get("title", "")), _key_words(right.get("title", ""))
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= threshold


def merge_problems(by_role: dict[str, list[dict]]) -> list[dict]:
    """Combines the specialists' problem lists, keeping one entry per problem and who reported it."""
    merged: list[dict] = []
    for role, problems in by_role.items():
        for problem in problems:
            twin = next((kept for kept in merged if same_problem(kept, problem)), None)
            if twin is None:
                merged.append({**problem, "reported_by": [role]})
            else:
                twin["reported_by"].append(role)
                if SEVERITY_ORDER[problem["severity"]] < SEVERITY_ORDER[twin["severity"]]:
                    twin["severity"] = problem["severity"]
    return sorted(merged, key=lambda problem: SEVERITY_ORDER[problem["severity"]])


@dataclass
class TeamResult:
    problems: list[dict]
    runs: dict[str, RunResult]

    @property
    def total_tokens(self) -> int:
        return sum(run.usage.total for run in self.runs.values())

    @property
    def total_tool_calls(self) -> int:
        return sum(run.tool_calls for run in self.runs.values())

    @property
    def raw_problem_count(self) -> int:
        return sum(len((run.findings or {}).get("problems") or []) for run in self.runs.values())


def review_with_specialists(run_specialist: Callable[[str], RunResult], roles: tuple[str, ...] = ("swe", "dba", "qa")) -> TeamResult:
    """run_specialist(role) runs that role's agent on the task and returns its RunResult."""
    runs = {role: run_specialist(role) for role in roles}
    by_role = {role: (run.findings or {}).get("problems") or [] for role, run in runs.items()}
    return TeamResult(merge_problems(by_role), runs)


class AskSpecialistArgs(BaseModel):
    role: str = Field(description="Which specialist to ask: swe, dba or qa.")
    question: str = Field(min_length=10, description="A self-contained question. The specialist knows nothing about "
                                                     "your conversation, so name the issue, table, file or PR.")


def specialist_tool(run_specialist: Callable[[str, str], RunResult], roles: tuple[str, ...] = ("swe", "dba", "qa")) -> Tool:
    """A tool for a lead agent. run_specialist(role, question) runs a sub-agent and returns its RunResult."""

    def ask_specialist(role: str, question: str) -> str:
        if role not in roles:
            return f"ERROR kind=unknown_role: choose one of {', '.join(roles)}."
        result = run_specialist(role, question)
        findings: dict[str, Any] = result.findings or {}
        if not findings:
            return f"The {role} specialist stopped without an answer ({result.stop_reason})."
        problems = "\n".join(f"- [{p['severity']}] {p['title']}: {p['detail']}" for p in findings.get("problems") or [])
        evidence = "\n".join(f"- {e['ref']}: \"{e['quote']}\"" for e in (findings.get("evidence") or [])[:4])
        return (f"{role} specialist ({result.tool_calls} tool calls):\n{findings.get('summary', '')}\n"
                + (f"root cause: {findings['root_cause']}\n" if findings.get("root_cause") else "")
                + (f"problems:\n{problems}\n" if problems else "") + (f"evidence:\n{evidence}" if evidence else ""))

    return Tool("ask_specialist", "Hand a focused question to a specialist agent (swe, dba or qa) that has its own "
                "tools and context, and get back its short answer with evidence. Use it for a self-contained "
                "sub-question that needs many tool calls; do simple lookups yourself.", ask_specialist, AskSpecialistArgs)
