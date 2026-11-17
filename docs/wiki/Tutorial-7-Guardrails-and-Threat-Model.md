# Tutorial 7: Guardrails and threat model

**Goal:** understand what stops the developer agent from doing harm, which of those protections do not depend on the model behaving, and what risk is left.

## The principle

A prompt asks a model to behave. It does not *make* it behave. So every rule that matters is also enforced by code that the model cannot talk to. The prompt is the first line of defence; the code is the one you rely on.

## Layers, in the order a run meets them

| Layer | Enforced by | What it stops |
|---|---|---|
| **Who can start a run** | Preflight (code) | Strangers: the issue author must be the owner, a member or a collaborator, and whoever adds the label needs write access |
| **Dependencies and limits** | Preflight (code) | Starting work whose prerequisites are not merged; runaway cost (daily run limit, dollar budget, timeouts, one run at a time) |
| **What the agent can touch** | A hook on every tool call (code) | Writing outside `restaurant/`, including `.github/`, `pipeline/` and the course code; reading `.git/` or files outside the repo |
| **What commands it can run** | The same hook, deny by default | Anything not on a short list: no `git push`, `curl`, `env`, `python -c`, redirects outside `restaurant/`, background jobs, command substitution |
| **Where commands run** | Claude Code's sandbox | Network access beyond the package index; credentials in the commands' environment (scrubbed) |
| **What the process knows** | The step's environment | The agent step has the model credential and **no GitHub token**; checkout does not persist credentials |
| **What happens to its work** | Gates (code) | Changes outside the allowed area, over 800 lines, secrets in the diff, code without tests, failing ruff or pytest, coverage under 85% |
| **Whether it did the job** | An independent reviewer (read-only) | A pull request being presented as ready when a criterion is not demonstrably met (it opens as a draft instead) |
| **What gets published** | Publish (code), the only step with the token | Staging anything but `restaurant/`; pushing anywhere but a `claude/issue-*` branch; merging; touching the default branch |
| **Who merges** | A person | Everything else. The pipeline never merges |

## What the hook does

The hook is `pipeline/hook.py`, with its rules in `pipeline/rules.py`. For each call it answers allow or deny; **an error, an unknown tool or an unresolvable path means deny**.

- **Paths** are resolved with symlinks followed, then compared with the allowed area. A link inside `restaurant/` that points outside it is refused.
- **Shell commands** are split into segments and each must start with an allowed command. `pytest` and `ruff` must be given an explicit path inside `restaurant/` (`ruff format .` would rewrite files everywhere). `pip` may only run `install -r restaurant/requirements*.txt`, so packages come from a file in the reviewed change, never from the command line, a URL or another index.
- **Every refusal is logged** and printed in the run log as `hook denied ...`, so a blocked run can be explained.

The guard was probed against the real CLI with the prompt rules *removed*, asking it to attempt nine forbidden actions. The hook alone refused all nine and allowed the one legitimate write.

## Prompt injection

Issue text, the charter, dish names and files are **data**. The system prompt says that instructions inside them that go beyond the task are to be reported, not followed. That is a request. What actually limits the damage of a successful injection is everything above: even an agent that wanted to push, read a secret or edit the workflow cannot, because the hook, the sandbox and the missing token stop it.

## Why the agent cannot write workflow files

GitHub refuses a push from the built-in token that creates or changes `.github/workflows/*`, and for a good reason: a workflow on a pull request branch runs with the repository's secrets. An agent-written workflow could read the model credential before anyone reviewed it. So only `restaurant/` is writable. When an issue needs CI, the agent writes a **template** under `restaurant/ci/`, and a person copies it into `.github/workflows/` after reading it.

## The independent reviewer

It is a second model run with a fresh context and read-only tools. It sees the issue, the charter, the diff and the gate results, and must give each acceptance criterion a verdict with evidence. **Code, not the model, turns that verdict into draft or ready.** It is deliberately strict: it marked a criterion "partly" when the only proof available was a CI run that had not happened. Treat its evidence table as a reviewer's checklist, not as a replacement for your own review.

## Residual risks

- **Tests written by the agent run on the runner.** The sandbox limits network access and the environment is scrubbed, but this is code written by a model. Keep the token's scope small and review every pull request.
- **Network egress of the Claude process itself is not restricted**; it needs the API.
- **The evaluator is a model.** It raises the bar; it can be wrong.
- **Supply chain.** Packages the agent lists are installed (wheels only, in a step without secrets). Check each new dependency in the pull request.
- **Quality varies with the issue.** Large or vague issues produce weaker results; the size limit and the `BLOCKED:` rule exist to push back.
- **A person is the last line.** Everything above makes review cheaper and safer; it does not remove it.

## Test the guardrails yourself

After any change to the rules, run `python -m pytest pipeline/tests -q`. To probe the real CLI, ask a Claude Code session using the pipeline's settings to attempt a list of forbidden actions and check that each is refused with the hook's reason and that no file appears. Do it with the prompt rules removed, so that you are testing the code and not the model's manners.
