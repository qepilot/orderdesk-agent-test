# Tutorial 5: Writing issues the pipeline can build

**Goal:** write an issue that a developer agent can finish and that the reviewer can judge. The pipeline is only as good as the issue.

## The shape

Every task issue in this project has the same sections, because the tooling reads them:

```markdown
**Depends on:** #12, #14

## Goal
One sentence: what exists afterwards that did not before.

## Scope
- The concrete things to build, with file or endpoint names where you know them.

## Acceptance criteria
- [ ] A checkable statement.
- [ ] Another one.

## Tests required
- What kinds of tests prove the criteria.

## Out of scope
- What this issue deliberately does not do.

---
_Rules for every task: see #5. Nothing here starts until a maintainer adds the label `claude-ready`._
```

- `**Depends on:**` is read by preflight. Every issue listed must be **closed** (merged) or the run is refused. Use `none` if there are no dependencies.
- The footer line `Rules for every task: see #N` points at the **project charter**, which the developer and the reviewer both receive.
- The `## Acceptance criteria` checkboxes are what the independent reviewer judges, one by one. Keep that heading exact.

## Rules for good criteria

1. **Provable by a test.** "The cart is fast" is not checkable. "Adding 40 distinct dishes to a cart returns within 200 ms in a test with a fake clock" is, if you really need it.
2. **Observable behaviour, not implementation.** "`POST /api/v1/orders` with the same `Idempotency-Key` returns the original order and creates no second one."
3. **One behaviour per criterion.** If a criterion has "and" in the middle, the reviewer cannot give it a clean verdict.
4. **Include the failure cases.** "A wrong token returns 404, not 403" is the kind of line that prevents a security bug.
5. **Nothing the pipeline cannot prove.** "The CI workflow passes on a pull request" was in an early issue; the reviewer rightly called it unprovable, so it became "a test parses the CI template and asserts it runs the check script". If a criterion needs a real pull request run, a person, or a container, move it to the pull request checklist, not the criteria.

## Size

- Aim for **a pull request under about 600 changed lines**. Above 800 the gates refuse it. If an issue is too big, split it before labelling.
- Separate the database from the endpoints from the screens. In this project the tables, the migration runner, the repository layer, each endpoint group and each page are different issues, which is why they are small and independent.

## Dependencies

Order matters because later work reads earlier work. The developer is told to read what the dependencies built. Describe contracts in the earlier issue (names, shapes, error codes) so the later one can rely on them.

## What not to put in an issue

- **Anything under `.github/`.** The agent may only write inside `restaurant/`. GitHub does not let the built-in token push workflow files, and a workflow on a pull request branch would run with the repository's secrets. Ask for a *template* under `restaurant/ci/` instead, and install it yourself.
- **Secrets, real card numbers or personal data.** Use obvious fake values.
- **Instructions to the agent about how to behave.** Behaviour rules belong in the charter, once. Text in an issue is treated as *data describing the task*; instructions in it that go beyond the task are reported, not followed.
- **Ambiguity you hope the agent will guess.** The agent is told to stop and ask (`BLOCKED:`). That is correct behaviour, so remove the ambiguity instead.

## The charter

The charter issue is the one document every task shares. It states the goal, the scope of version 1, the stack, the conventions (money in integer cents, layers, one check command), the definition of done and the guardrails. Read it before writing tasks; edit it deliberately, and before work starts, because changing it mid-project changes what "correct" means. It is never developed itself.

## Who may write issues

Preflight only proceeds when the **issue author** is the owner, a member or a collaborator, and the **person who added the label** has write access. An outsider cannot get code written by opening an issue. If you want a stranger's report built, open your own issue that restates it.
