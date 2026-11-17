# Tutorial 8: Troubleshooting runbook

Every entry below happened while building this pipeline. Find the symptom, read the cause, apply the fix.

## First, find out what stopped

1. Read the **status comment** on the issue. It usually says what stopped.
2. Open the **workflow run** and see which step is red or skipped.
3. In the *Develop* step log, look for lines starting `hook denied`: each is a command or file access the guard refused, with the reason.
4. Read the evaluation and gate tables in the pull request, if one was opened.

## Runbook

| Symptom | Cause | Fix |
|---|---|---|
| Failed `claude-develop.yml` runs appear **on a push**, and the label does nothing | GitHub rejected the workflow file as invalid (the error is not shown anywhere obvious). Real example: `${{ runner.temp }}` used in a job-level `env`, where that context is not allowed | Run `actionlint .github/workflows/*.yml`. CI (`pipeline-tests`) now lints every workflow, so this cannot merge |
| Comment: *not started: waiting for dependencies ... #N* | An issue listed under `Depends on:` is still open. The charter counts: it is never delivered by a pull request | Merge and close the dependency; for the charter, close it yourself to accept it. Then re-add the label |
| Comment: *not started: daily limit reached: N runs in the last 24 hours* | The cost guard. Refused runs and invalid-file runs count too | Raise the repository **variable** `CLAUDE_PIPELINE_MAX_RUNS_PER_DAY`, then re-add the label |
| You set the variable but the limit did not change | It was created under the **Secrets** tab, has a different name, or is scoped to an environment. The job log shows `PIPELINE_MAX_RUNS_PER_DAY: 6` | Create it on the **Variables** tab as a repository variable with the exact name |
| Comment: *not started: the issue was not written by the owner, a member or a collaborator* | Untrusted author: its text must not drive code changes | Open your own issue restating the task |
| Comment: *not started: ... a pull request for this issue is already open* | An earlier pull request is open on a `claude/issue-N-*` branch | Close it, then re-add the label |
| Comment: the **sandbox self-test failed**, with `apply-seccomp: write /proc/self/setgroups (nested userns is capability-restricted ...)` | The runner image does not allow the sandbox's user-namespace setup. Seen on the `ubuntu-latest` image (26.04), not on 24.04 or 22.04; a bare `bwrap` check passes there, which is why the check runs the real sandbox | Keep `runs-on: ubuntu-24.04`. Do not move the pin until the self-test passes on the newer image |
| The CLI warns *Sandbox disabled: ... socat not installed* | The sandbox needs `socat` as well as `bubblewrap` | The workflow installs both |
| The agent stops with `BLOCKED: ... pip is blocked` or cannot install packages | Only the repository is writable in the sandbox, so a system-wide install cannot work; and the command rules allow only one install form | Fixed: the agent creates `.venv` in the repo (`python -m venv --system-site-packages .venv`) and runs `.venv/bin/pip install -r restaurant/requirements.txt`. If you see it again, read the `hook denied` lines |
| `hook denied Bash: 'cd' is not allowed` | Agents often write `cd restaurant && ...` | `cd` is allowed into `restaurant/` only, and the prompt asks for commands from the repository root. A denial here is harmless |
| The push fails: *refusing to allow a GitHub App to create or update workflow ... without `workflows` permission* | The issue asked for a file under `.github/workflows/`. GitHub never lets the built-in token do that | Rewrite the issue: the agent writes a template under `restaurant/ci/`, a person installs it ([Tutorial 5](Tutorial-5-Writing-Issues-for-the-Pipeline.md)) |
| The pull request opens as a **draft** with `needs-human`, and one criterion is "partly" | The reviewer could not prove it from the diff. Real example: "CI passes on a pull request" | Read the evidence column. Fix the work, or rewrite the criterion to something a test can prove |
| *Independent evaluation* says "did not return a verdict" | The reviewer's structured result was refused or malformed | Fixed: the guard allows the structured-output tool. The raw reply is saved in the artifact's `evaluation.json` |
| The publish step cannot open the pull request (403) | **Allow GitHub Actions to create and approve pull requests** is off | Tick it in Settings, Actions, General |
| GitHub's own CI does not run on the pull request | PRs opened with the built-in token do not trigger workflows | Expected. The pipeline ran the gates itself. To get GitHub's CI, use a personal access token or an app for the publish step |
| `git add` stages nothing and publish says "nothing to commit" | A pathspec that matches nothing aborts the whole `git add` | Fixed: only existing paths are passed |
| A run finishes with the label still on the issue and nothing happens on a second try | Only *adding* the label triggers a run | Remove `claude-ready` and `needs-human`, then add `claude-ready` again |
| Artifact download fails in a restricted environment | The artifact is on a host that environment cannot reach | Use the job log, which prints gate results, the evaluator verdict, denials and costs |
| `.pyc` files, `.coverage` or `.venv/` appear in a diff | Build artifacts at the repository root | `.venv/` and caches are ignored by the checks; delete a stray `.coverage`; make sure `.gitignore` covers it |

## Questions that came up

**Why does a refused run count against the daily limit?** The limiter counts workflow runs, because that is what the API exposes. It is a cost guard, not an accounting system; raise the variable while you debug and lower it afterwards.

**Can I retry without removing the label?** No. A run starts when the label is *added*.

**Why did the agent stop with a question instead of guessing?** Because the rules say to. An issue that contradicts the charter or leaves a criterion ambiguous should be fixed in the issue, not worked around in code.

**Can the agent change the pipeline to loosen a rule?** No. `pipeline/` and the workflows are outside its writable area; the gates and the staging step also refuse them.
