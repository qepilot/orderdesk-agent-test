"""Claude Code PreToolUse hook: every tool call the developer agent makes passes through here first.

Deny by default and fail closed: an exception, an unknown tool or a path we cannot resolve all mean "no". The hook is
what stops a prompt-injected or simply mistaken agent from writing outside restaurant/, reading the git config, or running
commands that were never on the list. The prompt asks nicely; this enforces.

Protocol: the event arrives as JSON on stdin; to refuse, print a JSON decision and exit 0.
"""

from __future__ import annotations

import json
import os
import sys

from .rules import bash_verdict, read_allowed, to_repo_rel, write_allowed

WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
READ_TOOLS = {"Read": "file_path", "Glob": "path", "Grep": "path"}
RETURN_TOOLS = {"StructuredOutput"}      # how a model hands back a result that must match --json-schema; touches nothing


def decide(event: dict, root: str) -> tuple[bool, str]:
    tool = event.get("tool_name", "")
    data = event.get("tool_input") or {}
    cwd = event.get("cwd") or root
    if tool in RETURN_TOOLS:
        return True, ""
    if tool == "Bash":
        return bash_verdict(str(data.get("command", "")), root, cwd)
    if tool in WRITE_TOOLS:
        path = str(data.get(WRITE_TOOLS[tool], ""))
        rel = to_repo_rel(path, root, cwd) if path else None
        if rel is None or not write_allowed(rel):
            return False, f"{tool} on '{path}' is not allowed: only files under restaurant/ and restaurant workflows"
        return True, ""
    if tool in READ_TOOLS:
        path = data.get(READ_TOOLS[tool])
        if tool == "Glob" and str(data.get("pattern", "")).startswith(("/", "~")) or ".." in str(data.get("pattern", "")):
            return False, "Glob patterns must stay inside the repository"
        if path in (None, ""):
            return True, ""
        if not read_allowed(to_repo_rel(str(path), root, cwd)):
            return False, f"{tool} on '{path}' is not allowed (outside the repository or inside .git)"
        return True, ""
    return False, f"the tool '{tool}' is not available in this pipeline"


def deny(reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": reason}})


def main() -> int:
    try:
        event = json.load(sys.stdin)
        allowed, reason = decide(event, os.environ.get("PIPELINE_REPO_ROOT") or os.getcwd())
    except Exception as error:                 # fail closed
        print(deny(f"guard hook error: {error}"))
        return 0
    if not allowed:
        print(deny(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
