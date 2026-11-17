# Reference

## Commands

| Command | What it does |
|---|---|
| `python -m assistant investigate N` | Investigate issue N (offline fixtures, or a live model if configured) |
| `python -m assistant review N --role swe\|dba\|qa` | Review pull request N |
| `python -m assistant investigate N --repo OWNER/NAME` | Read the issue from real GitHub (needs a live model) |
| `... --post-comment` | Post the findings as a comment, or edit the assistant's earlier one (bot comments only) |
| `python -m assistant eval [--case issue-101] [--role qa]` | Run the evaluation cases and print the report |
| `python -m pytest -q` | The course's offline tests |
| `python -m pytest pipeline/tests -q` | The pipeline's tests |
| `python -m pipeline <stage>` | The pipeline stages: `preflight`, `selftest`, `develop`, `gates`, `evaluate`, `publish`, `fail` (run by the workflow) |
| `actionlint .github/workflows/*.yml` | Lint workflow files (`pip install actionlint-py`) |

## Course agent settings (`.env`)

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `standin` forces the offline stand-in; `claude-code` uses the Claude Code CLI |
| `CLAUDE_CODE_MODEL` | With `claude-code`: a CLI model alias; empty means the default |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_FAST_MODEL` | An OpenAI-compatible endpoint (ignored with `claude-code`) |
| `AGENT_MAX_STEPS` / `AGENT_MAX_SECONDS` / `AGENT_MAX_TOTAL_TOKENS` / `AGENT_MAX_FINAL_REJECTIONS` | Size of the harness's hard stops (defaults 25 / 300 / 400000 / 3) |
| `GITHUB_TOKEN` | For `--repo` against real GitHub |
| `EMBED_MODEL`, `EMBED_BASE_URL`, `EMBED_API_KEY` | Optional real embeddings for the retrieval lab |

## Repository secrets and variables

| Name | Kind | Meaning |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | **Secret** | Your Claude login for the CLI in workflows (`claude setup-token`) |
| `CLAUDE_PIPELINE_MAX_RUNS_PER_DAY` | Variable | Default 6 |
| `CLAUDE_PIPELINE_BUDGET_USD` | Variable | Default 5 per developer attempt |
| `CLAUDE_PIPELINE_MODEL` | Variable | Model alias for developer and reviewer |
| `CLAUDE_PIPELINE_SANDBOX_MODE` | Variable | `strict` (default) or `weaker-nested` |
| `CLAUDE_PIPELINE_SANDBOX` | Variable | `1` (default) or `0` (debug only) |

## Labels

| Label | Set by | Meaning |
|---|---|---|
| `claude-ready` | a person | **Starts the pipeline** when added to an issue |
| `claude-in-progress` | the pipeline | A run is working on the issue |
| `needs-human` | the pipeline | The run stopped, or opened a draft; a person must look |
| `investigate` | a person | Starts the investigate workflow on that issue (if enabled) |

## Limits and thresholds

| What | Value |
|---|---|
| Changed lines per pull request | hard stop at 800 (aim for about 600) |
| Coverage of `restaurant/app` | at least 85% |
| Runs per 24 hours | 6 by default (variable) |
| Developer attempts per run | 2 (one repair) |
| Developer budget | $5 per attempt (variable) |
| Developer timeout | 25 minutes per attempt; the job stops after 75 |
| Issue text length | at most 20,000 characters |

## Gates

`paths`, `size`, `secrets`, `tests_present`, `install_requirements`, `ruff`, `pytest` (with coverage when `restaurant/app` exists), `migration_check` (when a check script exists), `dependency_audit` (warning only).

## Preflight checks

The issue is open, is a task (not `[Epic]` or the charter) and is not a pull request; its author is `OWNER`, `MEMBER` or `COLLABORATOR`; the label was added by someone with `write`, `maintain` or `admin` access; it references the charter; every `Depends on` issue is closed; no open pull request on `claude/issue-N-*`; under the daily limit.

## Files

| Path | Purpose |
|---|---|
| `pipeline/rules.py` | The deterministic rules: paths, commands, size, secrets, parsing |
| `pipeline/hook.py` | The guard hook run on every tool call |
| `pipeline/preflight.py` | Pre-run checks |
| `pipeline/selftest.py` | The sandbox self-test |
| `pipeline/agent.py` | Runs the developer: settings, command line, prompt, environment |
| `pipeline/gates.py` | The quality gates |
| `pipeline/evaluator.py` | The independent reviewer and the ready-or-draft decision |
| `pipeline/publish.py` | Stage, commit, push, open the pull request |
| `pipeline/report.py` | Comment and pull request text |
| `pipeline/gh.py` | A tiny GitHub REST client |
| `assistant/` | The course agent (`llm.py` holds the Claude Code provider) |
| `workshop/` | The OrderDesk practice system the course agent investigates |
| `restaurant/` | The application the pipeline builds |
| `docs/wiki/` | The source of these wiki pages |
