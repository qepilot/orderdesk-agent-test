"""Module 1: talking to a model through the OpenAI-compatible chat completions API.

One HTTP endpoint, POST {base_url}/chat/completions, is spoken by OpenAI, OpenRouter, LiteLLM,
Azure OpenAI, vLLM, Ollama, LM Studio and most company gateways. We call it with plain httpx so
that every byte sent to the model is visible; there is no SDK and no framework in between.

Settings come from the environment (see .env.example):

    LLM_BASE_URL     default https://openrouter.ai/api/v1
    LLM_API_KEY      the key for that endpoint (not needed for a local server)
    LLM_MODEL        the model id exactly as the endpoint lists it
    CLAUDE_CODE_MODEL  with claude-code only: a CLI model alias such as "sonnet" (empty = the CLI default)
    LLM_PROVIDER     "standin" forces the offline stand-in even when a key is present;
                     "claude-code" uses the Claude Code CLI (`claude -p`) as the model, with no API key
    LLM_TEMPERATURE  optional; left out of the request when unset (some models reject it)
    LLM_MAX_TOKENS   optional cap on the length of one reply
    LLM_EXTRA_BODY   optional JSON object merged into every request (gateway-specific switches)
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class ModelError(RuntimeError):
    """The model call failed. kind is a stable word the harness and the reports can count."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


@dataclass
class ToolCall:
    """One tool call requested by the model. args is None when the JSON did not parse."""

    id: str
    name: str
    arguments: str                    # the raw JSON text, exactly as the model wrote it
    args: dict | None = None
    parse_error: str | None = None


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Reply:
    """What one model call returned, in the two shapes we need: parsed, and as a message to append."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    seconds: float = 0.0

    def as_message(self) -> dict:
        """The assistant message to append to the conversation, in the API's own format."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
                for call in self.tool_calls
            ]
        return message


class ChatModel(Protocol):
    """Anything with this method can drive the agent: a real endpoint, a scripted stand-in, a test fake."""

    name: str

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply: ...


def parse_tool_calls(raw_calls: list[dict] | None) -> list[ToolCall]:
    calls = []
    for index, raw in enumerate(raw_calls or []):
        function = raw.get("function") or {}
        arguments = function.get("arguments") or "{}"
        call = ToolCall(id=raw.get("id") or f"call_{index}", name=function.get("name") or "", arguments=arguments)
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                call.args = parsed
            else:
                call.parse_error = "arguments must be a JSON object"
        except json.JSONDecodeError as error:
            call.parse_error = f"arguments are not valid JSON ({error.msg} at position {error.pos})"
        calls.append(call)
    return calls


class OpenAICompatibleModel:
    """A chat model behind POST {base_url}/chat/completions."""

    def __init__(self, model: str, *, base_url: str = DEFAULT_BASE_URL, api_key: str = "",
                 temperature: float | None = None, max_tokens: int | None = None, timeout: float = 120.0,
                 max_retries: int = 3, extra_body: dict | None = None, client: httpx.Client | None = None):
        self.name = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.extra_body = extra_body or {}
        self._client = client or httpx.Client(timeout=timeout)

    def build_request(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> dict:
        """The JSON body of the request. Print it when you want to see exactly what the model receives."""
        body: dict[str, Any] = {"model": self.name, "messages": messages}
        if tools:
            body["tools"] = tools
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        body.update(self.extra_body)
        body.update(options)
        return body

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        body = self.build_request(messages, tools, **options)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        started = time.monotonic()
        data = self._post_with_retries(body, headers)
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise ModelError("bad_response", f"no choices in the response: {json.dumps(data)[:300]}") from None
        usage = data.get("usage") or {}
        return Reply(
            content=message.get("content") or "",
            tool_calls=parse_tool_calls(message.get("tool_calls")),
            finish_reason=choice.get("finish_reason") or "stop",
            usage=Usage(usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0),
            model=data.get("model") or self.name,
            seconds=time.monotonic() - started,
        )

    def _post_with_retries(self, body: dict, headers: dict) -> dict:
        """Retries what is worth retrying (rate limits, overload, timeouts) with exponential backoff."""
        last = "no attempt made"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(2 ** attempt + random.random(), 30))
            try:
                response = self._client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
            except httpx.TimeoutException:
                last = "timeout"
                continue
            except httpx.HTTPError as error:
                last = f"network error: {error}"
                continue
            if response.status_code in RETRYABLE_STATUS:
                last = f"HTTP {response.status_code}: {response.text[:200]}"
                continue
            if response.status_code >= 400:   # our request is wrong: retrying the same bytes cannot help
                kind = {401: "auth", 403: "auth", 404: "not_found"}.get(response.status_code, "bad_request")
                raise ModelError(kind, f"HTTP {response.status_code}: {response.text[:400]}")
            try:
                return response.json()
            except ValueError:
                last = f"response is not JSON: {response.text[:200]}"
        raise ModelError("unavailable", f"gave up after {self.max_retries + 1} attempts; last problem: {last}")


CLAUDE_CODE_PROTOCOL = """How tools work in this session (this overrides any impression from your environment):
- The tools in the TOOLS list are NOT callable directly. Never try to invoke them as native tools, and never report \
that tools are unavailable or "not found": that is a misunderstanding.
- The ONLY way to use a tool is to name it in the `tool_calls` list of your structured reply. The harness runs it \
and shows you the result in the next turn's conversation.
- If you are not finished, your reply must contain at least one entry in `tool_calls`. Do not stop to ask for \
permission or explain what you would do; request the next tool.
- When you are finished, request the tool that delivers the final result (for example submit_findings) in \
`tool_calls`. A reply with an empty `tool_calls` list ends the run without a result."""


class ClaudeCodeModel:
    """A chat model served by the Claude Code CLI (`claude -p`), so no API key is needed.

    The CLI has no tool-calling endpoint we can plug our own tools into, so each call is stateless: we render the
    tool descriptions and the whole conversation into one prompt and ask for a JSON answer in a fixed shape
    (text plus a list of tool calls). The harness, its guards and its graders are untouched; only the transport
    differs. The CLI's own tools are switched off and it runs in an empty directory, so it sees nothing but the prompt.
    """

    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Text for the user or your reasoning; may be empty."},
            "tool_calls": {
                "type": "array",
                "description": "Tools to call now. Empty when you are finished and need no tool.",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"},
                                   "arguments_json": {"type": "string", "description": "The arguments as a JSON object text."}},
                    "required": ["name", "arguments_json"],
                },
            },
        },
        "required": ["content", "tool_calls"],
    }

    def __init__(self, model: str = "", *, timeout: float = 240.0, max_retries: int = 2, executable: str | None = None):
        self.name = f"claude-code:{model or 'default'}"
        self.cli_model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.executable = executable or shutil.which("claude") or "claude"
        self._cwd = tempfile.mkdtemp(prefix="claude-code-model-")

    # -- prompt -----------------------------------------------------------------------------------

    @staticmethod
    def render(messages: list[dict], tools: list[dict] | None) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt) for one call."""
        system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        system = (system + "\n\n" if system else "") + CLAUDE_CODE_PROTOCOL
        lines = [
            "You are the model inside a tool-calling agent loop. You cannot run anything yourself; you can only ask the "
            "harness to call the tools below. Follow the system prompt above.",
            "",
            "TOOLS (call by name; arguments must match the JSON schema):",
            json.dumps([t.get("function", t) for t in (tools or [])], ensure_ascii=False),
            "",
            "CONVERSATION SO FAR:",
        ]
        for message in messages:
            role = message.get("role")
            if role == "system":
                continue
            if role == "user":
                lines.append(f"[user]\n{message.get('content') or ''}")
            elif role == "tool":
                lines.append(f"[tool result for call {message.get('tool_call_id')}]\n{message.get('content') or ''}")
            elif role == "assistant":
                if message.get("content"):
                    lines.append(f"[assistant said]\n{message['content']}")
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    lines.append(f"[assistant called tool {call.get('id')}] {function.get('name')}({function.get('arguments')})")
        lines += ["", "Now produce your next step as JSON: put any text in `content` and every tool you want called now in "
                  "`tool_calls` (arguments_json is a JSON object as text). Use an empty `tool_calls` list only when you "
                  "are finished and no tool is needed."]
        return system, "\n".join(lines)

    # -- call -------------------------------------------------------------------------------------

    def complete(self, messages: list[dict], tools: list[dict] | None = None, **options: Any) -> Reply:
        system, prompt = self.render(messages, tools)
        command = [self.executable, "-p", "--output-format", "json", "--json-schema", json.dumps(self.OUTPUT_SCHEMA),
                   "--tools", "", "--no-session-persistence", "--system-prompt", system or "You are a helpful assistant."]
        if self.cli_model:
            command += ["--model", self.cli_model]
        started = time.monotonic()
        data = self._run_with_retries(command, prompt)
        structured = data.get("structured_output")
        if not isinstance(structured, dict):
            structured = self._parse_loose(data.get("result", ""))
        calls = parse_tool_calls([
            {"id": f"call_{int(started * 1000) % 10_000_000}_{index}",
             "function": {"name": item.get("name", ""), "arguments": item.get("arguments_json") or "{}"}}
            for index, item in enumerate(structured.get("tool_calls") or []) if isinstance(item, dict)
        ])
        usage = data.get("usage") or {}
        used_in = (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) \
            + (usage.get("cache_creation_input_tokens") or 0)
        return Reply(content=str(structured.get("content") or ""), tool_calls=calls,
                     finish_reason="tool_calls" if calls else "stop",
                     usage=Usage(used_in, usage.get("output_tokens") or 0),
                     model=self.name, seconds=time.monotonic() - started)

    @staticmethod
    def _parse_loose(text: str) -> dict:
        """The CLI normally returns structured_output; if it answered in plain text, accept a JSON object inside it."""
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {"content": text, "tool_calls": []}

    def _run_with_retries(self, command: list[str], prompt: str) -> dict:
        last = "no attempt made"
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(2 ** attempt + random.random(), 20))
            try:
                done = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=self.timeout,
                                      cwd=self._cwd)
            except subprocess.TimeoutExpired:
                last = "timeout"
                continue
            except FileNotFoundError:
                raise ModelError("unavailable", "the `claude` CLI was not found on PATH") from None
            if done.returncode != 0:
                last = f"exit {done.returncode}: {(done.stderr or done.stdout)[:300]}"
                continue
            try:
                data = json.loads(done.stdout)
            except ValueError:
                last = f"output is not JSON: {done.stdout[:200]}"
                continue
            if data.get("is_error"):
                last = f"CLI reported an error: {str(data.get('result'))[:300]}"
                continue
            return data
        raise ModelError("unavailable", f"gave up after {self.max_retries + 1} attempts; last problem: {last}")


# -- configuration -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMStatus:
    ready: bool
    model: str
    base_url: str
    reason: str

    def __str__(self) -> str:
        state = "ready" if self.ready else "NOT ready"
        return f"LLM {state}: model={self.model or '-'} endpoint={self.base_url} ({self.reason})"


def _is_local(base_url: str) -> bool:
    return (urlsplit(base_url).hostname or "") in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def llm_status(purpose: str = "agent") -> LLMStatus:
    """Says whether a real model can be called, and what is missing when it cannot."""
    base_url = os.getenv("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL
    model = _model_name(purpose)
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "standin":
        return LLMStatus(False, model, base_url, "stand-in mode chosen with LLM_PROVIDER=standin")
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "claude-code":
        if not shutil.which("claude"):
            return LLMStatus(False, model, "claude-code", "the `claude` CLI is not on PATH")
        return LLMStatus(True, model, "claude-code", "Claude Code CLI, no API key needed")
    if not model:
        return LLMStatus(False, model, base_url, "set LLM_MODEL in .env")
    if not os.getenv("LLM_API_KEY", "").strip() and not _is_local(base_url):
        return LLMStatus(False, model, base_url, "set LLM_API_KEY in .env")
    return LLMStatus(True, model, base_url, "configured")


def make_model(purpose: str = "agent", **overrides: Any) -> OpenAICompatibleModel:
    """Builds the configured model. purpose="fast" uses LLM_FAST_MODEL when set (summaries, judges)."""
    status = llm_status(purpose)
    if not status.ready:
        raise RuntimeError(str(status))
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "claude-code":
        return ClaudeCodeModel(status.model, **{k: v for k, v in overrides.items() if k in {"timeout", "max_retries"}})
    temperature = os.getenv("LLM_TEMPERATURE", "").strip()
    max_tokens = os.getenv("LLM_MAX_TOKENS", "").strip()
    extra = os.getenv("LLM_EXTRA_BODY", "").strip()
    settings: dict[str, Any] = {
        "base_url": status.base_url,
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "temperature": float(temperature) if temperature else None,
        "max_tokens": int(max_tokens) if max_tokens else None,
        "extra_body": json.loads(extra) if extra else None,
    }
    settings.update(overrides)
    return OpenAICompatibleModel(status.model, **settings)


def _model_name(purpose: str) -> str:
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "claude-code":
        return os.getenv("CLAUDE_CODE_MODEL", "").strip()     # an alias such as "sonnet"; empty = the CLI's default
    main = os.getenv("LLM_MODEL", "").strip()
    if purpose == "fast":
        return os.getenv("LLM_FAST_MODEL", "").strip() or main
    return main
