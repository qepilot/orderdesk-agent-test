# Tutorial 6: Setup checklist

**Goal:** make a repository run the `claude-ready` pipeline. Work through the list in order; each item says how to check it.

## 1. Files

The pipeline is these parts of this repository:

| Path | Purpose |
|---|---|
| `.github/workflows/claude-develop.yml` | The pipeline workflow (trigger: the label `claude-ready`) |
| `.github/workflows/pipeline-tests.yml` | CI for the pipeline itself: lints every workflow file with `actionlint` and runs its tests |
| `.github/workflows/investigate-issue.yml` | Optional: investigates issues ([Tutorial 3](Tutorial-3-Investigate-a-Real-Issue.md)) |
| `pipeline/` | The code behind each stage, with its tests in `pipeline/tests/` |
| `docs/claude-pipeline.md` | Reference notes next to the code |
| `restaurant/` | Where the agent writes the application. It must exist or be creatable |

Copy `pipeline/` and the two workflow files into your repository, keep the `restaurant/` path (or change it in `pipeline/rules.py`, the prompt in `pipeline/agent.py` and the workflow), and merge them to the **default branch**: issue events use the workflow file on the default branch.

## 2. The model credential (a secret)

The pipeline uses your Claude login, not an API key.

1. On a computer where you are logged in to Claude Code, run:

   ```bash
   claude setup-token
   ```

2. Copy the token it prints.
3. In the repository: **Settings, Secrets and variables, Actions, Secrets tab, New repository secret**. Name it exactly `CLAUDE_CODE_OAUTH_TOKEN` and paste the token.

Check: the workflow's *Develop* step shows no "credential" error. The token draws on your Claude plan.

## 3. Repository settings

| Setting | Where | Why |
|---|---|---|
| **Allow GitHub Actions to create and approve pull requests** (ticked) | Settings, Actions, General, Workflow permissions | Without it the publish step cannot open the pull request |
| Actions enabled | Settings, Actions, General | |

## 4. Variables (optional, the Variables tab, not Secrets)

| Name | Default | Effect |
|---|---|---|
| `CLAUDE_PIPELINE_MAX_RUNS_PER_DAY` | 6 | Cost guard: preflight refuses beyond this many runs in 24 hours (refused runs count too) |
| `CLAUDE_PIPELINE_BUDGET_USD` | 5 | Dollar budget per developer attempt |
| `CLAUDE_PIPELINE_MODEL` | CLI default | A model alias for the developer and reviewer |
| `CLAUDE_PIPELINE_SANDBOX_MODE` | `strict` | `weaker-nested` isolates less; only for runners where `strict` cannot work. Not recommended |
| `CLAUDE_PIPELINE_SANDBOX` | `1` | `0` skips the sandbox. For debugging only |

**Common mistake:** creating a value under the *Secrets* tab. Workflows read variables as `vars.NAME`; a secret of the same name is invisible to that. The job log prints the value each step received, for example `PIPELINE_MAX_RUNS_PER_DAY: 20`, so you can confirm.

## 5. The runner image

`claude-develop.yml` is pinned to `runs-on: ubuntu-24.04`. On the image behind `ubuntu-latest` (26.04 when this was written) the agent's sandbox cannot run commands (`apply-seccomp: ... nested userns is capability-restricted`). The workflow also installs `bubblewrap` and `socat`, which the sandbox needs, and relaxes the AppArmor user-namespace restriction. Move the pin only after the sandbox self-test passes on the newer image.

## 6. Labels

The pipeline creates `claude-in-progress` and `needs-human` itself. Create `claude-ready` once (Issues, Labels, New label), so people can find it. Creating the label starts nothing; **adding it to an issue** does.

## 7. Issues

Write the charter and the task issues ([Tutorial 5](Tutorial-5-Writing-Issues-for-the-Pipeline.md)). The charter is closed once accepted, because the first task depends on it and preflight requires dependencies to be closed. Do not label anything yet.

## 8. Verify before the first real run

1. Merge a change and check the Actions tab: **no failed `claude-develop.yml` run on the push.** A workflow that only listens for `issues` should never appear on a push; if it does, GitHub rejected the file. Run `actionlint` locally.
2. Add `claude-ready` to the first task. Expected: the status comment says *started*, then a pull request appears.
3. If it stops, read the comment first; then [Troubleshooting](Tutorial-8-Troubleshooting-Runbook.md).

## 9. Keep the guard honest

Whenever you change `pipeline/rules.py` or the prompt, run the tests (`python -m pytest pipeline/tests -q`). The rule tests include attack-shaped inputs (writes outside `restaurant/`, command substitution, `git push`, reading `.git`); a rule that gets looser should break a test on purpose.
