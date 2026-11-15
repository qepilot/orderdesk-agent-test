from assistant.findings import check_findings
from assistant.harness import BASE_SYSTEM_PROMPT, Agent, Approval, Limits, approve_all
from assistant.llm import ModelError
from assistant.tools import investigation_tools, tool_schemas, write_tools
from lab.faults import FlakyModel, broken_tool, flaky_tool
from lab.scripts import call
from lab.standin import ScriptedModel
from assistant.reliability import FallbackModel, with_retries


def agent_for(model, workspace, **options):
    tools = options.pop("tools", None) or investigation_tools(workspace)
    return Agent(model, tools, system=BASE_SYSTEM_PROMPT, final_check=check_findings, **options)


def test_schemas_are_valid_function_tools(workspace):
    for schema in tool_schemas(investigation_tools(workspace) + write_tools(workspace)):
        function = schema["function"]
        assert schema["type"] == "function" and function["name"] and len(function["description"]) > 40
        assert function["parameters"]["type"] == "object"


def test_runaway_loop_is_stopped(workspace, scripted):
    result = agent_for(scripted("runaway-loop"), workspace, limits=Limits(max_steps=8)).run("t")
    assert (result.status, result.stop_reason, result.steps) == ("stopped", "max_steps", 8)
    assert [record.kind for record in result.ledger][:4] == ["ok", "ok", "repeated_call", "repeated_call"]


def test_broken_calls_come_back_as_data(workspace, scripted):
    result = agent_for(scripted("broken-calls"), workspace).run("t")
    assert result.stop_reason == "submitted"
    assert [record.kind for record in result.ledger] == ["unknown_tool", "invalid_json", "invalid_arguments", "ok",
                                                         "sql_error", "ok", "ok"]


def test_invented_evidence_is_rejected_then_corrected(workspace, scripted):
    result = agent_for(scripted("invented-evidence"), workspace).run("t")
    assert [record.kind for record in result.ledger if record.name == "submit_findings"] == ["findings_rejected", "ok"]
    assert result.findings["verdict"] == "needs_more_info"


def test_no_final_answer(workspace, scripted):
    result = agent_for(scripted("no-final-answer"), workspace).run("t")
    assert (result.status, result.stop_reason, result.findings) == ("stopped", "no_final_answer", None)


def test_tool_call_and_token_budgets(workspace, scripted):
    assert agent_for(scripted("issue-101"), workspace, limits=Limits(max_tool_calls=3)).run("t").stop_reason == "max_tool_calls"
    assert agent_for(scripted("issue-101"), workspace, limits=Limits(max_total_tokens=5000)).run("t").stop_reason == "token_budget"


def test_planted_instructions_cannot_write_read_secrets_or_post(workspace, scripted):
    approvals = []

    def approver(tool, args):
        approvals.append(tool.name)
        return Approval(False, "reviewer said no")

    tools = investigation_tools(workspace) + write_tools(workspace)
    result = agent_for(scripted("issue-105-gullible"), workspace, tools=tools, approver=approver).run("t")
    kinds = [record.kind for record in result.ledger]
    assert kinds.count("write_refused") == 2 and "multiple_statements" in kinds
    assert "secret_file" in kinds and "not_approved" in kinds and approvals == ["post_comment"]
    assert "@" not in "".join(record.output for record in result.ledger if record.name == "run_sql")
    assert not list((workspace.out / "outbox").glob("comment_105_*"))


def test_approved_comment_is_posted_and_redacted(workspace):
    script = [{"calls": [call("post_comment", number=101, body="Contact quentin.dang123@example.test about it.")]},
              {"say": "done"}]
    tools = investigation_tools(workspace) + write_tools(workspace)
    result = Agent(ScriptedModel(script), tools, system="s", approver=approve_all, final_tool=None).run("t")
    assert result.ledger[0].ok
    posted = sorted((workspace.out / "outbox").glob("comment_101_*"))[-1].read_text()
    assert "[email redacted]" in posted and "@" not in posted


def test_model_error_stops_the_run_cleanly(workspace, scripted):
    result = agent_for(FlakyModel(scripted("issue-106"), fail_first=1), workspace).run("t")
    assert (result.status, result.stop_reason) == ("stopped", "model_error") and "503" in result.error
    recovered = agent_for(FallbackModel(FlakyModel(scripted("issue-106"), 1), scripted("issue-106")), workspace).run("t")
    assert recovered.stop_reason == "submitted"


def test_tool_failures(workspace, scripted):
    tools = investigation_tools(workspace)
    flaky = [flaky_tool(tool, fail_first=2) if tool.name == "run_sql" else tool for tool in tools]
    without_retry = agent_for(scripted("issue-106"), workspace, tools=flaky).run("t")
    assert "timeout" in [record.kind for record in without_retry.ledger]

    flaky = [with_retries(flaky_tool(tool, fail_first=2), sleep=lambda s: None) if tool.name == "run_sql" else tool
             for tool in tools]
    with_retry = agent_for(scripted("issue-106"), workspace, tools=flaky).run("t")
    assert with_retry.stop_reason == "submitted" and all(record.ok for record in with_retry.ledger)

    broken = [broken_tool(tool) if tool.name == "read_file" else tool for tool in tools]
    crashed = agent_for(scripted("issue-106"), workspace, tools=broken).run("t")
    assert "tool_failed" in [record.kind for record in crashed.ledger] and crashed.stop_reason == "submitted"


def test_fallback_does_not_hide_configuration_errors(scripted):
    class WrongKey:
        name = "wrong-key"

        def complete(self, messages, tools=None, **options):
            raise ModelError("auth", "HTTP 401")

    try:
        FallbackModel(WrongKey(), scripted("issue-106")).complete([])
        assert False, "an auth error must not be swallowed"
    except ModelError as error:
        assert error.kind == "auth"
