"""Module 4: the investigation as an explicit workflow (LangGraph).

The agent loop decides its own next step, which is right for the open-ended part (gathering
evidence). The steps around it are not open-ended: check the result, write the comment, wait for
a person, publish. Those are fixed, must happen in order, and must survive a restart, so they are
drawn as a graph with a checkpoint after every node.

    load_task -> investigate -> validate --ok--> draft -> human_review --approve/edit--> publish -> END
                      ^            |                           |
                      +--retry-----+ (at most once)            +--reject--> END

    validate fails twice -> draft (marked as needing a human investigator)

Only this file imports LangGraph. The nodes call the same Agent, checks and GitHub client as
everything else in the course.
"""

from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .findings import render_markdown

MAX_ATTEMPTS = 2
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class FlowState(TypedDict, total=False):
    kind: Literal["issue", "pr"]
    number: int
    title: str
    attempts: int
    findings: dict | None
    stop_reason: str
    feedback: list[str]                 # what validation objected to, passed to the next attempt
    draft: str
    decision: dict                      # {"action": "approve" | "edit" | "reject", "body": str, "by": str}
    published: dict | None
    log: Annotated[list[str], operator.add]     # appended to by every node


def validation_problems(state: FlowState) -> list[str]:
    """Checks written as code, applied to whatever the agent produced. No model is involved."""
    findings = state.get("findings")
    if not findings:
        return [f"The run ended without findings (stop reason: {state.get('stop_reason', 'unknown')})."]
    problems = []
    text = " ".join(str(value) for value in findings.values())
    if _EMAIL.search(text):
        problems.append("The findings contain an email address. Refer to customers by id.")
    if findings.get("verdict") == "defect_confirmed":
        sources = {item.get("source") for item in findings.get("evidence") or []}
        if len(sources) < 2:
            problems.append("A confirmed defect needs evidence from at least two kinds of source "
                            "(for example database and code).")
        if not findings.get("recommendations"):
            problems.append("A confirmed defect needs at least one recommendation.")
    if findings.get("confidence") == "low" and findings.get("verdict") in ("defect_confirmed", "request_changes"):
        problems.append("Low confidence does not support this verdict; use needs_more_info or gather more evidence.")
    return problems


def build_workflow(run_investigation: Callable[[FlowState], Any], github: Any, checkpointer: Any):
    """run_investigation(state) runs the agent and returns a RunResult. github needs get_issue,
    get_pull and post_comment. checkpointer is a LangGraph saver (in memory or SQLite)."""

    def load_task(state: FlowState) -> dict:
        item = github.get_issue(state["number"]) if state["kind"] == "issue" else github.get_pull(state["number"])
        return {"title": item["title"], "attempts": 0, "feedback": [],
                "log": [f"loaded {state['kind']} #{state['number']}: {item['title']}"]}

    def investigate(state: FlowState) -> dict:
        result = run_investigation(state)
        attempt = state.get("attempts", 0) + 1
        return {"findings": result.findings, "stop_reason": result.stop_reason, "attempts": attempt,
                "log": [f"investigation attempt {attempt}: {result.status} ({result.stop_reason}), "
                        f"{result.steps} steps, {result.tool_calls} tool calls"]}

    def validate(state: FlowState) -> Command[Literal["investigate", "draft"]]:
        problems = validation_problems(state)
        if not problems:
            return Command(goto="draft", update={"feedback": [], "log": ["validation passed"]})
        if state["attempts"] < MAX_ATTEMPTS:
            return Command(goto="investigate",
                           update={"feedback": problems, "log": [f"validation failed, retrying: {problems}"]})
        return Command(goto="draft", update={"feedback": problems,
                                             "log": [f"validation failed after {state['attempts']} attempts"]})

    def draft(state: FlowState) -> dict:
        if state.get("feedback"):
            body = ("The assistant could not produce findings that pass validation. A person needs to investigate.\n\n"
                    + "\n".join(f"- {problem}" for problem in state["feedback"]))
        else:
            body = render_markdown(state["findings"])
        return {"draft": body, "log": [f"drafted a comment of {len(body)} characters"]}

    def human_review(state: FlowState) -> Command[Literal["publish", "__end__"]]:
        # interrupt() saves the state and stops the graph here. When the run is resumed with
        # Command(resume=...), this node starts again from its first line and interrupt() returns
        # the value that was passed in. Keep everything before interrupt() free of side effects.
        decision = interrupt({"question": f"Post this comment on {state['kind']} #{state['number']}?",
                              "draft": state["draft"], "options": ["approve", "edit", "reject"]})
        action = decision.get("action")
        if action in ("approve", "edit"):
            return Command(goto="publish", update={"decision": decision, "log": [f"human decision: {action}"]})
        return Command(goto=END, update={"decision": decision, "published": None,
                                         "log": [f"human decision: reject ({decision.get('reason', 'no reason given')})"]})

    def publish(state: FlowState) -> dict:
        body = state["decision"].get("body") if state["decision"]["action"] == "edit" else state["draft"]
        receipt = github.post_comment(state["number"], body)
        return {"published": receipt, "log": [f"comment published: {receipt}"]}

    graph = StateGraph(FlowState)
    for name, node in [("load_task", load_task), ("investigate", investigate), ("validate", validate),
                       ("draft", draft), ("human_review", human_review), ("publish", publish)]:
        graph.add_node(name, node)
    graph.add_edge(START, "load_task")
    graph.add_edge("load_task", "investigate")
    graph.add_edge("investigate", "validate")
    graph.add_edge("draft", "human_review")
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=checkpointer)
