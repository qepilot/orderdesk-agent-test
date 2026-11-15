"""The live adapter, tested against a fake endpoint: request shape, parsing, retries, error kinds."""

import json

import httpx
import pytest

from assistant.llm import ModelError, OpenAICompatibleModel, llm_status, parse_tool_calls

TOOLS = [{"type": "function", "function": {"name": "get_issue", "description": "d", "parameters": {"type": "object"}}}]


def model_with(handler, **options):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleModel("test-model", base_url="https://llm.example.test/v1/", api_key="k", client=client, **options)


def test_request_and_response_shapes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"model": "test-model-2026", "choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_issue", "arguments": "{\"number\": 101}"}}]}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 15}})

    reply = model_with(handler).complete([{"role": "user", "content": "hi"}], tools=TOOLS)
    assert seen["url"] == "https://llm.example.test/v1/chat/completions" and seen["auth"] == "Bearer k"
    assert seen["body"] == {"model": "test-model", "messages": [{"role": "user", "content": "hi"}], "tools": TOOLS}
    assert reply.tool_calls[0].args == {"number": 101} and reply.usage.total == 135 and reply.finish_reason == "tool_calls"
    assert reply.as_message()["tool_calls"][0]["function"]["arguments"] == "{\"number\": 101}"


def test_optional_settings_are_sent_only_when_set():
    body = OpenAICompatibleModel("m", temperature=0, max_tokens=500, extra_body={"seed": 7}).build_request([], None)
    assert body == {"model": "m", "messages": [], "temperature": 0, "max_tokens": 500, "seed": 7}


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("assistant.llm.time.sleep", lambda seconds: None)
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    assert model_with(handler).complete([]).content == "ok" and len(attempts) == 3


def test_error_kinds(monkeypatch):
    monkeypatch.setattr("assistant.llm.time.sleep", lambda seconds: None)
    for status, kind in [(401, "auth"), (404, "not_found"), (400, "bad_request"), (503, "unavailable")]:
        with pytest.raises(ModelError) as error:
            model_with(lambda request, status=status: httpx.Response(status, text="no"), max_retries=1).complete([])
        assert error.value.kind == kind


def test_malformed_tool_arguments_are_kept_for_the_harness():
    calls = parse_tool_calls([{"id": "c", "function": {"name": "read_file", "arguments": "{\"path\": "}},
                              {"id": "d", "function": {"name": "x", "arguments": "[1]"}}])
    assert calls[0].args is None and "not valid JSON" in calls[0].parse_error and calls[1].parse_error


def test_status_from_environment(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert not llm_status().ready
    monkeypatch.setenv("LLM_MODEL", "some/model")
    assert "LLM_API_KEY" in llm_status().reason
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    assert llm_status().ready                      # a local server needs no key
    monkeypatch.setenv("LLM_PROVIDER", "standin")
    assert not llm_status().ready


# -- Claude Code CLI provider ------------------------------------------------------------------


def test_claude_code_prompt_contains_tools_and_conversation():
    from assistant.llm import ClaudeCodeModel
    tools = [{"type": "function", "function": {"name": "add", "description": "add", "parameters": {"type": "object"}}}]
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "thinking", "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "add", "arguments": '{"a": 1}'}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "RESULT"}]
    system, prompt = ClaudeCodeModel.render(messages, tools)
    assert system.startswith("SYS") and "NOT callable directly" in system and "tool_calls" in system
    for needle in ('"name": "add"', "[user]\nQ", "add({\"a\": 1})", "RESULT"):
        assert needle in prompt


def test_claude_code_parses_structured_output(monkeypatch):
    import json, subprocess
    from assistant.llm import ClaudeCodeModel
    payload = {"structured_output": {"content": "hi", "tool_calls": [{"name": "add", "arguments_json": '{"a": 1, "b": 2}'}]},
               "usage": {"input_tokens": 3, "cache_read_input_tokens": 10, "output_tokens": 4}}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(payload), ""))
    reply = ClaudeCodeModel(executable="claude").complete([{"role": "user", "content": "x"}], tools=[])
    assert reply.tool_calls[0].name == "add" and reply.tool_calls[0].args == {"a": 1, "b": 2}
    assert reply.finish_reason == "tool_calls" and reply.usage.input_tokens == 13 and reply.usage.output_tokens == 4


def test_claude_code_accepts_json_in_plain_text_and_reports_failures(monkeypatch):
    import json, subprocess
    import pytest
    from assistant.llm import ClaudeCodeModel, ModelError
    assert ClaudeCodeModel._parse_loose('sure: {"content": "a", "tool_calls": []}')["content"] == "a"
    assert ClaudeCodeModel._parse_loose("no json here") == {"content": "no json here", "tool_calls": []}
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    with pytest.raises(ModelError) as error:
        ClaudeCodeModel(executable="claude", max_retries=1).complete([{"role": "user", "content": "x"}])
    assert error.value.kind == "unavailable" and "boom" in str(error.value)


def test_claude_code_provider_selection(monkeypatch):
    import shutil
    from assistant.llm import ClaudeCodeModel, make_model
    monkeypatch.setenv("LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("LLM_MODEL", "openrouter/ignored-id")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    assert llm_status().ready and llm_status().model == ""          # the OpenRouter id is not used
    assert isinstance(make_model(), ClaudeCodeModel)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert not llm_status().ready and "claude" in llm_status().reason
