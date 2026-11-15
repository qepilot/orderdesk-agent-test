# The `claude-ready` development pipeline

Adding the label **`claude-ready`** to an issue starts `.github/workflows/claude-develop.yml`. It develops that one issue, tests it, has the result independently evaluated, and opens a pull request. A person reviews and merges. Nothing else triggers it: not creating an issue, not other labels, not comments.

> **Honest status.** The rules, the guard hook, the gates, the evaluator and the publish logic are covered by 150 tests and were exercised against the real Claude Code CLI (a tiny task end to end, and a probe of the guard hook). The workflow itself has **not run on GitHub yet**. Expect to fix details on the first real run, and read "What is not verified" below.

## What happens

| Stage | Done by | What it does |
|---|---|---|
| 1. Preflight | plain code | Refuses unless: the issue is open and is a task (not the charter or epic); its author is the owner, a member or a collaborator (issue text is untrusted input); whoever added the label has write access; every issue it depends on is closed (merged); no pull request for it is open; fewer than 6 runs in 24 hours. All reasons are posted in one comment. |
| 2. Develop | Claude Code, inside guardrails | Writes the code and tests under `restaurant/`. Never commits or pushes. |
| 3. Gates | plain code | Changed files are all in the allowed area; at most 800 changed lines; no secrets in the diff; application code comes with tests; `ruff`; `pytest` with 85% coverage of `restaurant/app`; migration check; dependency audit (warning only). |
| 4. Repair | Claude Code | If the gates failed: one more attempt, told exactly what failed. |
| 5. Evaluate | a second, independent Claude run (read-only) | Judges every acceptance criterion as met, partly or not met, with evidence (file and test), and reports guardrail findings against the charter. |
| 6. Publish | plain code, the only step with the GitHub token | Stages only allowed paths, commits, pushes `claude/issue-N-slug`, opens the pull request. **Draft plus `needs-human`** if any gate failed or any criterion is not met; ready for review only if everything passed. |

If the agent finds an acceptance criterion ambiguous, or a needed dependency missing, it stops with a `BLOCKED:` question. The pipeline posts that question on the issue and labels it `needs-human`; no pull request is opened.

The issue gets one status comment that is edited as the run advances (started, then pull request opened or stopped, with a link to the run). Labels used by the pipeline: `claude-in-progress` and `needs-human`; both are created automatically.

## Guardrails: what is enforced where

| Risk | Enforced by |
|---|---|
| Agent edits files outside `restaurant/` (including `pipeline/` and these workflows) | PreToolUse hook on every Write/Edit; path gate after the run; staging only allow-listed paths |
| Agent runs a dangerous command (`git push`, `curl`, `python -c`, `env`, redirects outside `restaurant/`, ...) | Hook with a deny-by-default command allow-list (`pipeline/rules.py`), plus `dontAsk` permission mode |
| Agent reads `.git/` or files outside the repository | Hook on Read, Glob, Grep and Bash |
| Agent pushes or merges | It has no GitHub token (environment scrubbed, `persist-credentials: false`); only the publish step has one, and it only pushes `claude/issue-*` branches. Never the default branch, never a merge |
| Credentials leak through commands the agent runs | `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`; command sandbox with network limited to the package index; the step fails if the sandbox does not work rather than run without it |
| Prompt injection through issue text | Only trusted authors can start a run; issue text is passed as marked data; the system prompt says so; the hook does not depend on the model obeying |
| Runaway cost or time | Dollar budget per attempt (`CLAUDE_PIPELINE_BUDGET_USD`, default 5), agent timeout, job timeout of 75 minutes, daily run limit, one run at a time |
| Oversized or unreviewable change | 800 changed line hard limit (the charter says about 600) |
| Secrets or card data in code | Secret scan on the diff; the evaluator checks the charter's card-data and secret rules; the evaluation issue adds permanent invariant tests |
| Starting a task whose dependencies are not merged | Preflight checks the `Depends on` issues are closed |

The prompt asks the agent to follow these rules too, but nothing above relies on that. In a probe with the rules removed from the prompt, the hook alone refused 9 of 9 forbidden actions (writes outside `restaurant/`, edits to `pipeline/` and the workflows, `git push`, `curl`, reading `.git/config`, `cat /etc/passwd`, `env`, a redirect outside the repo) and allowed the control write.

## One-time setup

1. The secret `CLAUDE_CODE_OAUTH_TOKEN` must exist (the investigate workflow already uses it).
2. **Settings, Actions, General, Workflow permissions: tick "Allow GitHub Actions to create and approve pull requests".** Without it the publish step cannot open a pull request.
3. Merge this change to the default branch (issue events use the workflow on the default branch).
4. Optional repository variables: `CLAUDE_PIPELINE_MODEL`, `CLAUDE_PIPELINE_BUDGET_USD` (default 5), `CLAUDE_PIPELINE_MAX_RUNS_PER_DAY` (default 6), `CLAUDE_PIPELINE_SANDBOX` (set to `0` only to debug the sandbox step; not recommended), `CLAUDE_PIPELINE_SANDBOX_MODE` (`strict`, the default, or `weaker-nested`; see below).

## Using it

1. Merge the issues in order (see the epic). Start with the foundation issue.
2. Add the label `claude-ready` to **one** issue whose dependencies are merged.
3. Watch the status comment. Review the pull request: read the acceptance table, the gate table and the evidence, then merge. Merging closes the issue, which unblocks the next ones.
4. To retry: close the draft pull request, remove the label `claude-ready` and add it again.

## The sandbox self-test

Before any development starts, the pipeline runs the real Claude Code sandbox with the agent's own settings and asks it to run one harmless command that leaves a mark on disk. If the mark is there, commands can run in the sandbox. If not, the run stops with the literal error posted on the issue; it never falls back to running unsandboxed. (A bare `bwrap` check is not enough: it passed on a runner where the agent's commands still failed.)

If `strict` fails, the self-test also tries the `weaker-nested` mode and reports whether it would work. That mode isolates less and is **never used unless you set the repository variable `CLAUDE_PIPELINE_SANDBOX_MODE` to `weaker-nested`**.

## What is not verified

- **The develop, evaluate and publish steps on GitHub's runners.** The first real run (on `ubuntu-26.04`) passed preflight and the branch setup, but the agent's shell commands failed in the sandbox, so it stopped without running tests. The self-test above exists to diagnose and fail fast on exactly that.
- **The publish step against GitHub.** Pushing with the extraheader and opening the pull request are unit tested with fakes, not run for real.
- **Quality on real issues.** The smoke test was a tiny function. Larger issues may need more than one repair attempt or a higher budget.
- **Pull requests opened with `GITHUB_TOKEN` do not trigger other workflows**, so `restaurant-ci.yml` will not run on them. The pipeline runs the same gates itself before opening the pull request; to also get GitHub's own checks on those pull requests, use a personal access token or an app for the publish step.

## Risks that remain

- Tests written by the agent run on the runner. The command sandbox limits network access and the environment is scrubbed, but this is code written by a model, so keep the token's scope small and review every pull request.
- The evaluator is a model too. It raises the bar and gives a reviewer an evidence table; it does not replace the review.
- Network egress of the Claude process itself is not restricted (it needs the API).
