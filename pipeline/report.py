"""Text for the status comment on the issue and for the pull request description."""

from __future__ import annotations

from .rules import acceptance_criteria, scan_secrets

MARKER = "<!-- claude-pipeline -->"
ICON = {"pass": "pass", "fail": "FAIL", "warn": "warn", "skip": "skipped"}


def status_comment(stage: str, run_url: str, details: str = "") -> str:
    body = f"{MARKER}\n**Claude pipeline: {stage}**\n\n"
    if details:
        body += details.strip() + "\n\n"
    return body + f"[Workflow run]({run_url})" if run_url else body


def _gate_table(gates: dict) -> str:
    rows = ["| Check | Result |", "|---|---|"]
    for check in gates.get("checks", []):
        rows.append(f"| {check['name']} | {ICON.get(check['status'], check['status'])} |")
    return "\n".join(rows)


def _criteria_table(context: dict, report: dict) -> str:
    criteria = acceptance_criteria(context["issue"]["body"])
    by_index = {c.get("index"): c for c in ((report.get("evaluation") or {}).get("criteria") or [])}
    rows = ["| # | Acceptance criterion | Verdict | Evidence |", "|---|---|---|---|"]
    for i, text in enumerate(criteria, 1):
        entry = by_index.get(i, {})
        rows.append(f"| {i} | {text.replace('|', '/')} | {entry.get('status', 'not evaluated')} | "
                    f"{str(entry.get('evidence', '')).replace('|', '/')[:300]} |")
    return "\n".join(rows)


def pr_body(context: dict, gates: dict, report: dict, developer: list[dict], new_deps: list[str], ready: bool,
            run_url: str) -> str:
    issue = context["issue"]
    cost = sum((d.get("cost_usd") or 0) for d in developer) + (report.get("cost_usd") or 0)
    parts = [f"Closes #{issue['number']}", "",
             "Written by the automated pipeline from the issue's scope. **A person must review it before merging.**"
             + ("" if ready else " This is a **draft** because at least one check or criterion did not pass."), "",
             "## Gates", _gate_table(gates), f"\nChanged files: {len(gates.get('files', []))}, changed lines: {gates.get('lines')}.", "",
             "## Independent evaluation", _criteria_table(context, report)]
    summary = (report.get("evaluation") or {}).get("summary")
    if summary:
        parts += ["", f"Reviewer summary: {summary}"]
    if report.get("problems"):
        parts += ["", "**Open problems:**"] + [f"- {p}" for p in report["problems"]]
    findings = (report.get("evaluation") or {}).get("guardrail_findings") or []
    if findings:
        parts += ["", "**Guardrail findings:**"] + [f"- [{f.get('severity')}] {f.get('text')}" for f in findings]
    if new_deps:
        parts += ["", "## New dependencies (check the licence and need)"] + [f"- `{d}`" for d in new_deps]
    parts += ["", "## Run", f"- Developer attempts: {len(developer)}; model cost shown by the CLI: about ${cost:.2f}"]
    if run_url:
        parts += [f"- [Workflow run and trace artifact]({run_url})"]
    parts += ["", "🤖 Generated with [Claude Code](https://claude.com/claude-code)"]
    text = "\n".join(parts)
    leaked = scan_secrets(text)
    return text if not leaked else "(description withheld: it matched a secret pattern)"
