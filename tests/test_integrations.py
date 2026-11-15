"""MCP, the LangGraph workflow, and the optional extensions."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from assistant.app import build_assistant, issue_task, pr_task
from assistant.github import LocalGitHub
from assistant.harness import BASE_SYSTEM_PROMPT, Agent
from assistant.mcp_client import McpToolbox, workshop_server
from assistant.memory import LessonStore
from assistant.multi import merge_problems, review_with_specialists, specialist_tool
from assistant.skills import discover_skills, skill_tool, skills_prompt
from assistant.tools import final_tool, github_tools, code_tools
from assistant.findings import check_findings
from assistant.workflow import build_workflow, validation_problems
from lab.scripts import SCRIPTS
from lab.standin import ScriptedModel


def test_mcp_round_trip_and_agent_run(workspace):
    with McpToolbox(workshop_server()) as toolbox:
        assert toolbox.server_name == "orderdesk-workshop"
        names = {spec["name"] for spec in toolbox.list_tools()}
        assert {"run_sql", "describe_schema", "search_knowledge"} <= names
        assert "3000" in toolbox.call_tool("run_sql", {"query": "SELECT COUNT(*) AS n FROM orders"})
        assert "write_refused" in toolbox.call_tool("run_sql", {"query": "DELETE FROM orders"})
        tools = github_tools(workspace) + code_tools(workspace) + toolbox.tools() + [final_tool()]
        result = Agent(ScriptedModel(SCRIPTS["issue-106"]), tools, system=BASE_SYSTEM_PROMPT, final_check=check_findings).run("t")
        assert result.stop_reason == "submitted" and result.findings["verdict"] == "no_defect_found"


def flow_parts(workspace, script, fail_first=0):
    github = LocalGitHub(workspace.github, workspace.out / "outbox")
    remaining = {"failures": fail_first}

    def run_investigation(state):
        if remaining["failures"]:
            remaining["failures"] -= 1
            raise RuntimeError("worker crashed")
        task = issue_task(state["number"])
        return build_assistant(ScriptedModel(SCRIPTS[script]), workspace=workspace, task=task).agent.run(task)

    return github, run_investigation


def test_workflow_survives_a_crash_and_waits_for_approval(workspace, tmp_path):
    github, run_investigation = flow_parts(workspace, "issue-104", fail_first=1)
    config, database = {"configurable": {"thread_id": "t1"}}, str(tmp_path / "flow.sqlite")
    with SqliteSaver.from_conn_string(database) as saver:
        flow = build_workflow(run_investigation, github, saver)
        with pytest.raises(RuntimeError):
            flow.invoke({"kind": "issue", "number": 104}, config)
        assert flow.get_state(config).next == ("investigate",)
    with SqliteSaver.from_conn_string(database) as saver:        # a new process would start here
        flow = build_workflow(run_investigation, github, saver)
        paused = flow.invoke(None, config)
        assert paused["__interrupt__"][0].value["options"] == ["approve", "edit", "reject"]
        assert flow.get_state(config).next == ("human_review",) and "published" not in paused
        done = flow.invoke(Command(resume={"action": "edit", "body": "Edited by a person."}), config)
    assert open(done["published"]["saved_to"]).read() == "Edited by a person."


def test_workflow_reject_publishes_nothing(workspace):
    github, run_investigation = flow_parts(workspace, "issue-106")
    flow = build_workflow(run_investigation, github, InMemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    flow.invoke({"kind": "issue", "number": 106}, config)
    done = flow.invoke(Command(resume={"action": "reject", "reason": "not needed"}), config)
    assert done["published"] is None and "reject" in done["log"][-1]


def test_workflow_retries_once_then_escalates(workspace):
    github, run_investigation = flow_parts(workspace, "no-final-answer")
    flow = build_workflow(run_investigation, github, InMemorySaver())
    paused = flow.invoke({"kind": "issue", "number": 101}, {"configurable": {"thread_id": "t3"}})
    assert paused["attempts"] == 2 and "A person needs to investigate" in paused["draft"]


def test_validation_rules():
    assert validation_problems({"findings": None, "stop_reason": "max_steps"})
    weak = {"verdict": "defect_confirmed", "confidence": "high", "recommendations": ["x"],
            "evidence": [{"source": "database", "ref": "r", "quote": "q"}], "summary": "mail a@b.io"}
    problems = " ".join(validation_problems({"findings": weak}))
    assert "two kinds of source" in problems and "email" in problems


def test_skills_are_listed_cheaply_and_loaded_on_demand(workspace):
    skills = discover_skills()
    assert [skill.name for skill in skills] == ["security-review", "sql-performance-analysis", "test-coverage-assessment"]
    assert len(skills_prompt(skills)) < sum(len(skill.body) for skill in skills) / 3
    tool = skill_tool(skills)
    assert "CONCURRENTLY" in tool.fn(name="sql-performance-analysis")
    task = pr_task(204)
    assistant = build_assistant(ScriptedModel(SCRIPTS["pr-204"]), workspace=workspace, task=task,
                                extra_tools=[tool], extra_system=skills_prompt(skills))
    result = assistant.agent.run(task)
    assert result.stop_reason == "submitted" and "load_skill" in [record.name for record in result.ledger]


def test_lessons_need_a_person_and_are_retrieved_by_relevance(tmp_path):
    store = LessonStore(tmp_path / "lessons.jsonl")
    with pytest.raises(ValueError):
        store.add("x", tags="t", source="issue-101", verified_by=" ")
    store.add("When totals differ, look for a second query on order_items without a status filter.",
              tags="billing invoice total", source="issue-101", verified_by="lena")
    store.add("Table rebuild migrations drop indexes; compare index lists.", tags="database index migration",
              source="issue-102", verified_by="tomas")
    assert store.search("invoice total is wrong", 1)[0].source == "issue-101"
    assert "hints, not evidence" in store.prompt_for("slow query after migration") and store.prompt_for("zzz") == ""


def test_specialists_merge_duplicates_and_cost_more(workspace):
    def run_specialist(role):
        task = pr_task(201)
        return build_assistant(ScriptedModel(SCRIPTS[f"pr-201-{role}"]), workspace=workspace, role=role, task=task,
                               knowledge=False, planning=False).agent.run(task)

    team = review_with_specialists(run_specialist)
    assert team.raw_problem_count == 6 and len(team.problems) == 4
    shared = next(problem for problem in team.problems if len(problem["reported_by"]) == 2)
    assert set(shared["reported_by"]) == {"swe", "qa"}
    single = build_assistant(ScriptedModel(SCRIPTS["pr-201"]), workspace=workspace, task=pr_task(201)).agent.run(pr_task(201))
    assert team.total_tokens > single.usage.total * 0.8
    assert merge_problems({"a": [{"severity": "minor", "title": "No tests", "detail": ""}],
                           "b": [{"severity": "major", "title": "no tests", "detail": ""}]})[0]["severity"] == "major"


def test_lead_agent_delegates_and_keeps_its_context_small(workspace):
    def run_specialist(role, question):
        return build_assistant(ScriptedModel(SCRIPTS[f"pr-201-{role}"]), workspace=workspace, role=role, task=question,
                               knowledge=False, planning=False).agent.run(question)

    lead = build_assistant(ScriptedModel(SCRIPTS["pr-201-lead"]), workspace=workspace, task=pr_task(201), knowledge=False,
                           planning=False, extra_tools=[specialist_tool(run_specialist)])
    result = lead.agent.run(pr_task(201))
    assert result.stop_reason == "submitted", [(r.name, r.kind, r.output[:300]) for r in result.ledger if not r.ok]
    assert [record.name for record in result.ledger].count("ask_specialist") == 2
