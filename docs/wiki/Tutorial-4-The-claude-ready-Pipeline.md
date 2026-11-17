# Tutorial 4: The claude-ready pipeline, from label to pull request

**Goal:** follow one issue through the pipeline, know what each stage does and where to look, and retry when something stops.

Adding the label **`claude-ready`** to an issue starts `.github/workflows/claude-develop.yml`. Nothing else triggers it: not creating an issue, not other labels, not comments.

## The stages

| # | Stage | Done by | What happens |
|---|---|---|---|
| 1 | **Preflight** | plain code | Refuses unless the issue is open and is a task (not the charter or epic); its author is the owner, a member or a collaborator; whoever added the label has write access; every issue it depends on is closed; no pull request for it is already open; the daily run limit is not reached. All reasons are posted in one comment. |
| 2 | **Branch and dependencies** | plain code | Creates `claude/issue-N-slug`; installs the project's requirements if a file exists. |
| 3 | **Sandbox self-test** | Claude Code | Runs one harmless command through the agent's real sandbox and checks it left a mark on disk. Stops here, cheaply, if commands cannot run. |
| 4 | **Develop** | Claude Code in a sandbox | Writes code and tests under `restaurant/`; installs packages into a virtualenv in the repo; runs ruff and pytest. Cannot commit or push. |
| 5 | **Gates** | plain code | Allowed paths only, at most 800 changed lines, no secrets, tests with the code, requirements install, ruff, pytest with 85% coverage, dependency audit (warning). |
| 6 | **Repair** | Claude Code | Only if the gates failed: one more attempt, told exactly what failed. |
| 7 | **Evaluate** | a second, read-only Claude run | Judges every acceptance criterion as met, partly or not met, with evidence (file and test), and reports guardrail findings. |
| 8 | **Publish** | plain code, the only step with the GitHub token | Stages only `restaurant/`, commits, pushes the branch, opens the pull request. **Draft plus `needs-human`** if any gate failed or any criterion is not met. Ready for review only when everything passed. |

If the agent finds an acceptance criterion ambiguous or a needed dependency missing, it stops and ends with a `BLOCKED:` question. The pipeline posts that question on the issue, adds `needs-human`, and opens no pull request.

## Run one

1. Make sure everything the issue depends on is merged and closed (`Depends on:` is the first line of the issue).
2. Add the label `claude-ready` to **one** issue. Only one development run goes at a time.
3. Watch the issue. A single **status comment** is edited as the run advances: *started*, then *pull request opened* (with a link) or *stopped, needs a person* (with the reason).
4. A run takes a few minutes (the first runs took between 1.7 and 3 minutes of workflow time). For the first real issue (the project scaffold) the result was a pull request with 18 files and 348 changed lines, all eight gates passing, five of five criteria met, and about $0.22 of model use shown by the CLI.

## Read the pull request

The description is written for a reviewer:

- **Gates table.** Each check with its result.
- **Independent evaluation table.** Each acceptance criterion, the verdict, and the evidence (a test name and file). Read the evidence, not just the verdict.
- **Reviewer summary and guardrail findings.** Usually low-severity notes: an unpinned dependency, a missing edge-case test, a stray file.
- **New dependencies.** Each one needs a licence and need check by you.
- **Run.** Attempts and model cost, with a link to the workflow run.

A pull request opened by the workflow does not trigger other workflows (GitHub's rule for the built-in token), so GitHub's own CI does not run on it. The pipeline runs the same gates itself before opening the pull request.

Merging the pull request closes the issue (its description says `Closes #N`), which unblocks the issues that depend on it. **A person always reviews and merges. The pipeline never merges.**

## When it stops

| You see | Meaning | Do this |
|---|---|---|
| Comment: *not started*, with reasons | Preflight refused | Fix the reason (usually: dependencies not merged, or the limit), then re-add the label |
| Comment: *stopped, needs a person* with a `BLOCKED:` question | The agent needs a decision | Answer by editing the issue to remove the ambiguity, then re-add the label |
| Comment: the sandbox self-test failed, with an error | Commands cannot run on this runner | See [Troubleshooting](Tutorial-8-Troubleshooting-Runbook.md) |
| A **draft** pull request labelled `needs-human` | A gate failed or a criterion is not met | Read the tables; fix by hand, or improve the issue and rerun |
| Nothing at all | The workflow file may be invalid, or the label name differs | Check the Actions tab; the file is linted by CI |

**To retry:** close any draft pull request, remove the labels `claude-ready` and `needs-human` from the issue, and add `claude-ready` again. Only the act of adding the label starts a run.

## Where to look when you need detail

1. The **status comment** on the issue: the short version.
2. The **workflow run** log (Actions tab): every step. In the *Develop* step, every command the guard refused is printed as `hook denied <tool>: <reason> | <input>`. That line usually explains a blocked run.
3. The **artifact** `pipeline-issue-N` on the run: the full developer and evaluator output, the gate report and the generated settings. Some restricted environments cannot download artifacts; the job log has the key facts.
