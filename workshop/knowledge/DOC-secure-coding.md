---
id: DOC-secure-coding
type: standard
date: 2026-02-14
title: Secure coding rules for OrderDesk
tags: security, sql injection, privacy
---

# Secure coding rules for OrderDesk

- SQL is always parameterised. Building SQL with string formatting or f-strings from request input is an
  injection vulnerability, including inside `LIKE` patterns and `LIMIT`.
- Validate and cap every numeric parameter.
- Do not return personal data that the caller does not need. List endpoints return ids, not emails.
- Secrets live in the secrets manager. `.env` files are never committed, logged or quoted.
- Automation with access to production data is read-only unless a person approves the specific write.
