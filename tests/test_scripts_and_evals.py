import pytest

from assistant.app import build_assistant
from assistant.evals import grade, judge_with_model, load_cases, task_for
from lab.scripts import SCRIPTS
from lab.standin import CannedModel, ScriptedModel

CASE_IDS = ["issue-101", "issue-102", "issue-103", "issue-104", "issue-105", "issue-106",
            "pr-201", "pr-202", "pr-203", "pr-204"]


def run(workspace, case, script=None, **options):
    assistant = build_assistant(ScriptedModel(SCRIPTS[script or case["id"]]), workspace=workspace, task=task_for(case), **options)
    return assistant.agent.run(task_for(case))


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_reference_script_passes_every_grader(workspace, case_id):
    case = load_cases(workspace.expected / "cases.json", ids=[case_id])[0]
    graded = grade(case, run(workspace, case))
    assert graded.passed, (graded.checks, graded.missed, graded.violations)
    assert graded.coverage == 1.0


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_reference_script_also_works_with_the_module_2_tool_set(workspace, case_id):
    case = load_cases(workspace.expected / "cases.json", ids=[case_id])[0]
    result = run(workspace, case, knowledge=False, planning=False)
    assert result.stop_reason == "submitted", [(r.name, r.kind, r.output[:200]) for r in result.ledger if not r.ok]


def test_flawed_scripts_fail_for_the_right_reasons(workspace):
    cases = {case["id"]: case for case in load_cases(workspace.expected / "cases.json")}
    shallow = grade(cases["issue-101"], run(workspace, cases["issue-101"], "issue-101-shallow"))
    assert not shallow.passed and not shallow.checks["location"] and "recommends refunding the customer" in shallow.violations
    gullible = grade(cases["issue-105"], run(workspace, cases["issue-105"], "issue-105-gullible"))
    assert not gullible.passed and not gullible.checks["safe"] and not gullible.checks["security_note"]


def test_role_filter(workspace):
    assert {case["id"] for case in load_cases(workspace.expected / "cases.json", role="dba")} >= {"issue-102", "pr-202"}


def test_model_judge_parses_and_survives_nonsense(workspace):
    case = load_cases(workspace.expected / "cases.json", ids=["issue-101"])[0]
    assert judge_with_model(CannedModel(['{"score": 0.9, "reason": "same cause"}']), case, {})["score"] == 0.9
    assert judge_with_model(CannedModel(["I think it is fine"]), case, {})["score"] == 0.0
