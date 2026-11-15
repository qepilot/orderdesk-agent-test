"""Module 4: using tools from an MCP server inside our own harness.

McpToolbox starts (or connects to) an MCP server, asks it which tools it has, and wraps each one
as an ordinary Tool. The agent loop does not change at all: to the harness an MCP tool is a
name, a description, a JSON schema and a function that returns text, like every other tool.

The MCP SDK is asynchronous and our loop is synchronous, so the toolbox keeps one event loop
running in a background thread and hands every call over to it. That also works inside Jupyter,
which already runs an event loop of its own.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any

from mcp import Client, StdioServerParameters

from .tools import Tool
from .workspace import COURSE_DIR


def workshop_server() -> StdioServerParameters:
    """How to launch this course's MCP server as a subprocess."""
    return StdioServerParameters(command=sys.executable, args=["-m", "assistant.mcp_server"], cwd=str(COURSE_DIR))


class McpToolbox:
    """A connection to one MCP server, usable from synchronous code.

        with McpToolbox(workshop_server()) as toolbox:
            tools = toolbox.tools()          # list[Tool] for the Agent

    server may be StdioServerParameters (a local subprocess) or a URL string (a remote server over
    Streamable HTTP).
    """

    def __init__(self, server: Any, *, prefix: str = "", timeout: float = 30.0):
        self.server = server
        self.prefix = prefix
        self.timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._client: Client | None = None
        self.server_name = ""

    # -- lifecycle ----------------------------------------------------------------------------

    def start(self) -> "McpToolbox":
        self._thread.start()
        self._ready = threading.Event()
        self._session = asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(self.timeout) or self._client is None:
            error = self._session.exception() if self._session.done() else None
            raise RuntimeError(f"could not connect to the MCP server: {error or 'timed out'}")
        return self

    def close(self) -> None:
        if self._client is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
            try:
                self._session.result(self.timeout)
            except Exception:       # the server process is going away anyway
                pass
            self._client = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def __enter__(self) -> "McpToolbox":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    async def _serve(self) -> None:
        """One task owns the connection from handshake to shutdown; calls arrive from other tasks."""
        self._stop = asyncio.Event()
        try:
            async with Client(self.server) as client:      # the MCP "initialize" handshake happens here
                self._client = client
                self.server_name = getattr(client.server_info, "name", "") or ""
                self._ready.set()
                await self._stop.wait()
        finally:
            self._ready.set()

    def _call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(self.timeout)

    # -- the two requests that matter -----------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """tools/list: what the server offers, as plain dicts (name, description, inputSchema)."""
        result = self._call(self._client.list_tools())
        return [{"name": tool.name, "description": tool.description or "", "inputSchema": tool.input_schema}
                for tool in result.tools]

    def call_tool(self, name: str, arguments: dict) -> str:
        """tools/call: runs one tool on the server and returns its text."""
        result = self._call(self._client.call_tool(name, arguments))
        text = "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")
        if result.is_error:
            return f"ERROR kind=mcp_tool_error: {(text or 'the server reported an error')[:300]}"
        return text

    def tools(self, only: set[str] | None = None) -> list[Tool]:
        """The server's tools wrapped for the harness. Arguments are validated by the server."""
        wrapped = []
        for spec in self.list_tools():
            if only is not None and spec["name"] not in only:
                continue
            wrapped.append(Tool(name=self.prefix + spec["name"], description=spec["description"],
                                fn=_caller(self, spec["name"]), parameters=spec["inputSchema"]))
        return wrapped


def _caller(toolbox: McpToolbox, remote_name: str):
    def call(**arguments) -> str:
        return toolbox.call_tool(remote_name, arguments)
    return call
