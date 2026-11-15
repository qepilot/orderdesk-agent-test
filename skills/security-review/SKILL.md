---
name: security-review
description: Checklist for reviewing a code change for security problems (injection, missing validation, personal data exposure, secrets, breaking authorisation). Load it for any pull request that adds an endpoint, builds SQL, or changes what an API returns.
---

# Security review of a change

Read the whole diff, then for every place where data enters from outside, follow it to where it is used.

1. **Injection.** Is any SQL, shell command, file path or template built by concatenating or formatting input?
   In this codebase every query must use `?` placeholders, including values inside `LIKE` and `LIMIT`.
   Compare with how the surrounding code does it (`read_file` the neighbouring functions).
2. **Validation.** Every parameter: type checked, range capped, empty value handled. What happens with `""`, `%`,
   a negative number, a very large number?
3. **Data exposure.** Does the response contain names, emails, addresses or payment data the caller does not need?
   List endpoints return ids.
4. **Secrets.** No keys or passwords in code, tests, logs or error messages.
5. **Contract.** Renamed or removed response fields break clients; check the API conventions in the knowledge base.
6. **Tests.** Is there a test with hostile input (a quote character, a wildcard, an oversized value)?

## Severity

- **blocker**: exploitable from the outside, or data loss or leak (injection, authorisation bypass, personal data in bulk).
- **major**: breaks clients, or leaks a little, or will fail under ordinary misuse.
- **minor**: hardening and hygiene.

## Output

One problem per finding, with the exact line, a concrete hostile input that demonstrates it where possible, and the
fix. Do not include working exploit strings beyond what is needed to show the problem.
