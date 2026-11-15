# Auto-investigating issues with GitHub Actions

`.github/workflows/investigate-issue.yml` runs the assistant on an issue and posts its findings as a comment.
It uses the Claude Code CLI as the model (`LLM_PROVIDER=claude-code`), so there is no OpenAI-compatible endpoint
and no model API key to manage, only one repository secret.

> **Honest status.** The CLI flags and the comment logic are covered by tests with fakes, and reading a real issue
> through `LiveGitHub` was run by hand. The workflow itself has not been run on GitHub yet: expect to fix a detail or
> two on the first run.

## One-time setup

1. On a computer where you are logged in to Claude Code, run `claude setup-token` and copy the token it prints.
2. In the repository: **Settings, Secrets and variables, Actions, New repository secret**. Name it
   `CLAUDE_CODE_OAUTH_TOKEN` and paste the token.
3. Make sure Actions are enabled for the repository. If the organisation forces read-only workflow permissions,
   allow write access for this repository (the workflow asks only for `contents: read` and `issues: write`).

Prefer an API key? Set `ANTHROPIC_API_KEY` as the secret instead and replace the `CLAUDE_CODE_OAUTH_TOKEN` lines in
the workflow with it.

## What starts a run

| Trigger | When |
|---|---|
| New issue | only if its author is the repo owner, an organisation member or a collaborator |
| Label `investigate` | on any issue; only people with triage rights can add labels |
| Actions tab, **Run workflow** | type the issue number |

Issues from anyone else are ignored until a maintainer adds the label. Issue text is untrusted input and every run
costs tokens, so strangers cannot start one.

## What it does and does not do

- Reads the issue and the commit list from GitHub; reads code, the database and the knowledge base from the checked
  out repository. All tools are read-only and the SQL guard still applies.
- Posts **one comment** with the findings, redacted for emails and similar personal data. If the run cannot finish, it
  posts a short note with the stop reason instead.
- The agent itself has no write tool. The comment is posted by the command line, after the run, not by the model.
- Keeps the trace as a workflow artifact for 14 days.
- Cost and time: a run takes roughly 1 to 3 minutes and 40k to 300k tokens of the account behind the token. The job
  stops after 20 minutes, and the harness has its own step, time and token limits (`AGENT_MAX_*` in the workflow).

## Trying it

```bash
gh workflow run investigate-issue.yml -f issue_number=1
```

or add the label `investigate` to an issue. Run it locally the same way the workflow does:

```bash
LLM_PROVIDER=claude-code GITHUB_TOKEN=... python -m assistant investigate 1 --repo OWNER/NAME
```

Add `--post-comment` to post the result.
