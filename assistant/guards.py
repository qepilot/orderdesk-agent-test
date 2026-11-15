"""Guards that live in code, outside the model's reach (Modules 2 and 5).

The model proposes; these functions decide. None of them asks the model for permission and none
can be talked out of its answer by text in an issue, a file or a tool result.
"""

from __future__ import annotations

import fnmatch
import re
import sqlite3
import time
from pathlib import Path


class ToolError(Exception):
    """A tool refuses or fails in a way the model can act on.

    kind is a short stable word (counted in reports); the message says what happened and what to do next.
    The harness turns it into the tool result "ERROR kind=<kind>: <message>" instead of crashing the run.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


# -- untrusted content ---------------------------------------------------------------------------


def untrusted(source: str, text: str) -> str:
    """Marks text that came from outside (issues, files, documents) as data, not instructions.

    The closing tag is neutralised inside the text so that content cannot "close" its own wrapper.
    The wrapper is a signal to the model, not a security boundary: the boundary is what tools can do.
    """
    safe = text.replace("</untrusted_content", "<\\/untrusted_content")
    return f'<untrusted_content source="{source}">\n{safe}\n</untrusted_content>'


# -- files -----------------------------------------------------------------------------------------

SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "*secret*", "*credentials*")
ALLOWED_SECRET_LOOKALIKES = (".env.sample", ".env.example")


def resolve_inside(root: Path, relative: str) -> Path:
    """Resolves a path given by the model and proves it is inside root and not a secret."""
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolError("path_outside_repo", f"'{relative}' is outside the repository. Use a path relative to its root.")
    name = candidate.name.lower()
    if name not in ALLOWED_SECRET_LOOKALIKES and any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_PATTERNS):
        raise ToolError("secret_file", f"'{relative}' may contain secrets and cannot be read. Continue without it.")
    return candidate


# -- SQL -------------------------------------------------------------------------------------------

_READ_VERBS = ("select", "with", "explain")
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex|grant|revoke)\b",
    re.IGNORECASE)
_STRINGS_AND_COMMENTS = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|--[^\n]*|/\*.*?\*/", re.DOTALL)
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def check_read_only_sql(query: str) -> str:
    """First layer: a readable refusal for anything that is not one read-only statement."""
    statement = query.strip().rstrip(";").strip()
    if not statement:
        raise ToolError("empty_query", "The query is empty.")
    bare = _STRINGS_AND_COMMENTS.sub(" ", statement)
    if ";" in bare:
        raise ToolError("multiple_statements", "Send exactly one statement per call.")
    if not bare.strip().lower().startswith(_READ_VERBS):
        raise ToolError("write_refused", "Only SELECT (or WITH ... SELECT) is allowed. This database access is read-only.")
    forbidden = _FORBIDDEN.search(bare)
    if forbidden:
        raise ToolError("write_refused",
                        f"'{forbidden.group(1).upper()}' is not allowed. This database access is read-only; "
                        "describe the change you would make in your findings instead.")
    return statement


def _authorizer(action, arg1, arg2, database, trigger):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def run_read_only(db_path: Path, query: str, *, max_rows: int = 50, timeout_seconds: float = 5.0):
    """Runs one read-only statement behind three independent layers and returns (columns, rows, truncated).

    1. check_read_only_sql: text check with a helpful message.
    2. SQLite authorizer: the database engine itself refuses every action except reading.
    3. The file is opened read-only (mode=ro), which is the equivalent of a read-only database user.
    Plus a row cap and a time limit, so one careless query cannot flood the context or hang the run.
    """
    statement = check_read_only_sql(query)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    deadline = time.monotonic() + timeout_seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    conn.set_authorizer(_authorizer)
    try:
        cursor = conn.execute(statement)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
    except sqlite3.OperationalError as error:
        if "interrupted" in str(error):
            raise ToolError("query_timeout", f"The query ran longer than {timeout_seconds:.0f} s. Narrow it down.") from None
        raise ToolError("sql_error", f"{error}. Check table and column names with describe_schema.") from None
    except sqlite3.DatabaseError as error:
        if "not authorized" in str(error) or "readonly" in str(error):
            raise ToolError("write_refused", "The database refused this statement: access is read-only.") from None
        raise ToolError("sql_error", str(error)) from None
    finally:
        conn.close()
    return columns, rows[:max_rows], len(rows) > max_rows


# -- output ----------------------------------------------------------------------------------------

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SECRET = re.compile(r"\b(?:sk|pk|pgk|ghp|gho|xox[bap])[-_][A-Za-z0-9_\-]{12,}\b")


def redact(text: str) -> str:
    """Last line of defence for anything that leaves a tool: masks email addresses and key-shaped strings."""
    text = _EMAIL.sub("[email redacted]", text)
    return _SECRET.sub("[secret redacted]", text)


def clip(text: str, max_chars: int) -> str:
    """Keeps the start and the end of a long text and says how much was cut."""
    if len(text) <= max_chars:
        return text
    head, tail = int(max_chars * 0.7), int(max_chars * 0.2)
    cut = len(text) - head - tail
    return f"{text[:head]}\n[... {cut} characters cut. Ask for a narrower range or query to see them ...]\n{text[-tail:]}"
