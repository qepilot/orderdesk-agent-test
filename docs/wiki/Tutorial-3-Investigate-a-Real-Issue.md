# Tutorial 3: Investigate a real GitHub issue

**Goal:** point the agent at a real issue in a real repository, read its findings, and have it post them as a comment that later runs update in place.
**Before you start:** finish [Tutorial 1](Tutorial-1-Quick-Start.md) and have a model configured ([Tutorial 2](Tutorial-2-Claude-Code-as-the-Model.md)).

> **What it investigates.** The agent's GitHub tool reads the real issue, but its code, database and knowledge tools read the local *practice system* (`workshop/`), the OrderDesk app. It is meaningful for OrderDesk-style issues (for example "invoice total does not match order total"), not for arbitrary projects.

## 1. Read an issue from GitHub

```bash
export GITHUB_TOKEN=<a token that can read issues in the repo>
```

```bash
LLM_PROVIDER=claude-code python -m assistant investigate 1 --repo qepilot/orderdesk-agent-test
```

`--repo OWNER/NAME` switches the GitHub tool from the offline fixtures to `api.github.com`. It needs a live model; without one the command stops with a clear message, because the stand-in scripts only know the practice numbers. A public repository can be read without a token, with GitHub's lower rate limit.

You get the findings printed in the terminal: verdict, root cause, evidence (each quote is checked against a real tool result), recommendations, regression tests, open questions and security notes.

## 2. Post the findings as a comment

```bash
LLM_PROVIDER=claude-code python -m assistant investigate 1 --repo qepilot/orderdesk-agent-test --post-comment
```

This needs a token with write access to issues. Three things make it safe:

- The agent itself has **no write tool**. The command line posts the comment after the run, not the model.
- The text is **redacted** once more (emails and similar) at the point where it leaves the program.
- A hidden marker (`<!-- engineering-assistant:investigation -->`) lets a rerun find its own earlier comment and **edit it** instead of adding another. Only comments written by a **bot** account are ever edited, so a person pasting the marker into their comment cannot get it overwritten. (A run started with your personal token posts as you, so it adds a new comment; in the workflow below it always comes from `github-actions[bot]`.)

## 3. Run it automatically with a workflow

`.github/workflows/investigate-issue.yml` runs the same command on GitHub:

| Trigger | When |
|---|---|
| New issue | only if its author is the repo owner, an organisation member or a collaborator |
| Label `investigate` | any issue; only people with triage rights can add labels |
| **Run workflow** (Actions tab) | you type the issue number |

Issues from strangers never start a run: issue text is untrusted input and every run costs model usage.

It needs the repository secret `CLAUDE_CODE_OAUTH_TOKEN` (see [Setup checklist](Tutorial-6-Setup-Checklist.md)). Try it:

```bash
gh workflow run investigate-issue.yml -f issue_number=1
```

> In this repository the workflow is currently **disabled** so that creating the restaurant issues would not start runs. Enable it with `gh workflow enable investigate-issue.yml`. If you do, remember that any new issue by the owner will start an investigation, which is meaningless for restaurant issues.

## 4. What to check in the result

- **Evidence is real.** Each evidence quote must be copied exactly from a tool result of that run, one short line. The harness rejects anything else and asks again.
- **Open questions are honest.** A good result lists what it did not check.
- **Security notes.** If the issue text contained instructions aimed at an AI assistant, they are reported there and not followed. The practice case 105 is built to test exactly this.
