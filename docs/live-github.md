# Optional: Using a Real GitHub Repository

The labs read issues and pull requests from files in `workshop/github/`, so that everybody gets the same data
with no network and no token. If your group wants the real thing (real issues, real pull requests, real
comments), this page shows how. Do it after Module 2. Nothing in the course requires it.

> **Honest status.** `LiveGitHub` is tested against a fake GitHub API (`tests/test_github.py`): the request
> paths and the mapping of responses are covered. It was not run against github.com while the course was
> written. Expect to adjust small things, and treat that as part of the exercise.

## 1. Put the practice application in a repository of your own

Create an empty **private** repository, then copy the practice application into it:

```bash
cp -r workshop/repo /tmp/orderdesk
```

```bash
cd /tmp/orderdesk && git init -b main && git add . && git commit -m "OrderDesk practice application"
```

```bash
git remote add origin https://github.com/YOUR-ORG/orderdesk-practice.git && git push -u origin main
```

`workshop/repo/.env` contains a **fake** key that exists so the labs can prove it is unreadable. It is harmless,
but delete it before pushing if your organisation scans for secrets.

## 2. Create the issues and pull requests

Each file in `workshop/github/issues/` has a `title`, a `body`, `labels` and `comments`. Create them by hand in
the web interface (six issues take five minutes), or with the GitHub CLI:

```bash
gh issue create --repo YOUR-ORG/orderdesk-practice --title "Customer #123: invoice total does not match order total" --body-file body.md
```

For the pull requests, create a branch per file in `workshop/github/pulls/`, apply the `.diff` with
`git apply`, push and open a pull request with the title and description from the `.json` file.

The numbers GitHub assigns will not be 101 to 106 and 201 to 204. That is fine for investigating by hand. The
evaluation cases and the stand-in scripts refer to the workshop numbers, so keep using the local fixtures for
Module 5.

## 3. A token with the smallest possible scope

Create a **fine-grained personal access token** limited to that one repository, with read-only access to
*Contents*, *Issues*, *Pull requests* and *Metadata*. Add it to `.env`:

```text
GITHUB_TOKEN=github_pat_...
```

Do not give it write access yet.

## 4. Point the assistant at it

```python
from assistant.app import build_assistant, issue_task
from assistant.github import LiveGitHub
from assistant.llm import make_model

github = LiveGitHub("YOUR-ORG/orderdesk-practice")        # reads GITHUB_TOKEN from the environment
print(github.list_issues())

assistant = build_assistant(make_model(), github=github, task=issue_task(1))
result = assistant.agent.run(issue_task(1))
```

Only the GitHub tools change. Code, database and operations tools still read the local workshop, which matches
the repository you pushed.

## 5. Posting comments, when you are ready

Posting is off twice over: `LiveGitHub` refuses unless created with `allow_comments=True`, and the harness asks
the approver before running `post_comment`. To post for real you need all of:

1. a token with **write** access to *Issues* (and *Pull requests* for PR comments),
2. `LiveGitHub("...", allow_comments=True)`,
3. `build_assistant(..., can_comment=True, approver=your_function)` with an approver that shows you the exact
   text and returns `Approval(True, ...)` only when you say yes, or the Module 4 workflow with this client.

Use the workflow. It validates the findings, formats the comment in code, and records the decision.

## What changes when the data is real

- **Sizes.** Real issues have long threads, real diffs are thousands of lines. Watch the clipping markers and
  the context budget (Module 3).
- **Rate limits.** The REST API allows a few thousand requests per hour per token. An agent in a loop can use
  them up; cache `get_issue` results if you run evaluations.
- **Untrusted text.** On a real repository anyone who can open an issue can write to your agent's context.
  Everything in Module 5, Lab G applies.
- **Other systems.** Check whether an official MCP server exists for the system you want before writing a
  connector (Module 4).
