"""Sandbox self-test: can the agent's shell commands actually run on this machine?

A plain "does bwrap start" check is not enough (it passed on a runner where the agent's commands still failed). This runs the
real thing: Claude Code with the same settings the developer agent uses, asked to run one harmless command that leaves a mark
on disk. If the mark is there, commands run inside the sandbox. If not, we have the literal error and we stop *before* spending
a developer run, and without ever falling back to running unsandboxed.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
from pathlib import Path

from .agent import SANDBOX_MODES, build_settings, clean_env, run_claude

PROMPT = """This is a sandbox self-test. Use the Bash tool exactly once, to run exactly this command:

{command}

Then reply with the literal text the tool returned. If the tool call failed or was refused, reply with the complete,
literal error message and nothing else. Do not retry and do not try anything else."""


def probe(mode: str, root: str, out_dir: Path, *, runner=run_claude, environ: dict | None = None, timeout: int = 240) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(6)
    marker_dir = Path(root, "restaurant", ".selftest")
    command = f"mkdir -p restaurant/.selftest && echo {nonce} > restaurant/.selftest/probe.txt"
    settings_path = out_dir / f"settings-selftest-{mode}.json"
    settings_path.write_text(json.dumps(build_settings(f"{sys.executable} -m pipeline.hook", sandbox=True,
                                                       sandbox_extra=SANDBOX_MODES[mode]), indent=2), encoding="utf-8")
    cli = ["claude", "-p", "--output-format", "json", "--permission-mode", "dontAsk", "--tools", "Bash",
           "--settings", str(settings_path), "--setting-sources", "user", "--no-session-persistence",
           "--max-budget-usd", "0.5"]
    env = clean_env(dict(os.environ if environ is None else environ))
    env["PIPELINE_REPO_ROOT"] = os.path.realpath(root)
    env["PYTHONPATH"] = os.path.realpath(root)
    result = runner(cli, PROMPT.format(command=command), cwd=root, env=env, timeout=timeout)
    probe_file = marker_dir / "probe.txt"
    ran = probe_file.is_file() and probe_file.read_text(encoding="utf-8").strip() == nonce
    shutil.rmtree(marker_dir, ignore_errors=True)               # our own marker directory, nothing else
    data = result["data"]
    return {"mode": mode, "ok": bool(ran), "timed_out": result["timed_out"], "returncode": result["returncode"],
            "model_report": str(data.get("result", ""))[:1500], "stderr": result.get("stderr", "")[-800:]}


def run_selftest(selected: str, root: str, out_dir: Path, **kwargs) -> dict:
    """Test the selected mode. If it fails, also test the weaker mode, for information only: it is never used automatically."""
    report = {"selected": selected, "results": [probe(selected, root, out_dir, **kwargs)]}
    report["ok"] = report["results"][0]["ok"]
    if not report["ok"] and selected == "strict":
        report["results"].append(probe("weaker-nested", root, out_dir, **kwargs))
    report["weaker_would_work"] = any(r["mode"] == "weaker-nested" and r["ok"] for r in report["results"])
    (out_dir / "selftest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def describe_failure(report: dict) -> str:
    lines = [f"The sandbox self-test failed in mode `{report['selected']}`: the agent's shell commands cannot run on this "
             "machine, so the run was stopped before any development started."]
    for result in report["results"]:
        lines.append(f"- mode `{result['mode']}`: {'works' if result['ok'] else 'FAILED'}"
                     + ("" if result["ok"] else f" — {result['model_report'][:400] or result['stderr'][:400] or 'no output'}"))
    if report.get("weaker_would_work"):
        lines.append("The weaker nested sandbox would work. It isolates less. To allow it, set the repository variable "
                     "`CLAUDE_PIPELINE_SANDBOX_MODE` to `weaker-nested` and add the label again.")
    return "\n".join(lines)
