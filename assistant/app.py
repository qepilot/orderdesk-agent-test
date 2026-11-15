"""Assembles the assistant from its parts. The CLI, the workflow, the evaluation and the notebooks
all build their agent here, so there is one place that says what the assistant is made of."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .context import ContextManager
from .findings import check_findings
from .guards import redact
from .harness import BASE_SYSTEM_PROMPT, Agent, Approval, Limits, deny_all
from .retrieval import Retriever, embedder_from_env
from .state import InvestigationState
from .tools import Tool, investigation_tools, knowledge_tools, state_tools, write_tools
from .tracing import Tracer
from .workspace import Workspace, default_workspace

ROLE_PROMPTS = {
    "swe": "You are working for a software engineer. Emphasise the code path from the API route to the data, the "
           "exact lines involved, breaking changes and security risks.",
    "dba": "You are working for a database administrator. Emphasise queries, execution plans, indexes, migrations, "
           "locking and how to apply a change safely on a large table.",
    "qa": "You are working for a QA engineer. Emphasise how to reproduce, why existing tests did not catch the "
          "problem, missing edge cases and the regression tests to add.",
}

PLANNING_PROMPT = """Planning and notes:
- For any task that needs more than two steps, call update_plan before gathering evidence and keep it current.
- Call record_note as soon as you establish a fact you will need in the final answer. Older tool results may be \
cleared from your context; your notes are not.
- Stop gathering when the evidence explains the report, you know how widespread it is, and you can name the fix. \
More calls after that only add cost."""

KNOWLEDGE_PROMPT = """The knowledge base (search_knowledge) holds past incidents, runbooks and engineering \
standards. Check it for similar past problems and for the agreed way to fix things. If the first search finds \
nothing useful, describe the mechanism in different words and search again."""


def issue_task(number: int) -> str:
    return (f"Investigate GitHub issue #{number} for the OrderDesk service. Verify what is reported, find the root "
            "cause if there is a defect, establish how widespread it is, and recommend a fix and regression tests.")


def pr_task(number: int) -> str:
    return (f"Review pull request #{number} for the OrderDesk service. Decide whether it is correct, complete and "
            "safe to merge. Report every problem you find with its severity, and say what tests are missing.")


@dataclass
class Assistant:
    agent: Agent
    state: InvestigationState | None
    tracer: Tracer | None
    workspace: Workspace
    tools: list[Tool]


_RETRIEVERS: dict[str, Retriever] = {}


def shared_retriever(workspace: Workspace, mode: str = "hybrid") -> Retriever:
    """Builds the index once per process; embedding the corpus again for every agent would be waste."""
    key = f"{workspace.knowledge}:{mode}"
    if key not in _RETRIEVERS:
        _RETRIEVERS[key] = Retriever(workspace.knowledge, mode, embedder_from_env() if mode != "keyword" else None)
    return _RETRIEVERS[key]


def build_assistant(model: Any, *, workspace: Workspace | None = None, role: str | None = None,
                    knowledge: bool = True, planning: bool = True, can_comment: bool = False,
                    approver: Callable[[Tool, dict], Approval] = deny_all, state_path: str | Path | None = None,
                    resume: bool = False,
                    task: str = "", limits: Limits | None = None, context_tokens: int | None = 30_000,
                    tracer: Tracer | None = None, extra_tools: list[Tool] | None = None,
                    extra_system: str = "", github: Any = None) -> Assistant:
    workspace = workspace or default_workspace()
    system = [BASE_SYSTEM_PROMPT]
    tools = investigation_tools(workspace, github)
    state = None
    if knowledge:
        tools += knowledge_tools(workspace, shared_retriever(workspace))
        system.append(KNOWLEDGE_PROMPT)
    if planning:
        if resume and state_path and Path(state_path).exists():
            state = InvestigationState.load(state_path)       # pick up where an earlier run stopped
        else:
            state = InvestigationState(task=task, path=str(state_path or ""))
        tools += state_tools(state)
        system.append(PLANNING_PROMPT)
    if can_comment:
        tools += write_tools(workspace, github)
    if role:
        system.append(ROLE_PROMPTS[role])
    if extra_system:
        system.append(extra_system)
    tools += extra_tools or []
    context = ContextManager(max_tokens=context_tokens, state=state) if context_tokens else None
    agent = Agent(model, tools, system="\n\n".join(system), limits=limits or Limits.from_env(), approver=approver,
                  final_check=check_findings, context=context, state=state, tracer=tracer, output_filter=redact)
    return Assistant(agent, state, tracer, workspace, tools)
