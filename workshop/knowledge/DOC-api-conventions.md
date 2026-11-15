---
id: DOC-api-conventions
type: standard
date: 2026-01-10
title: API conventions and compatibility policy
tags: api, compatibility, pagination
---

# API conventions and compatibility policy

- Response fields are part of the contract. Renaming or removing a field is a breaking change and needs a new
  API version and a deprecation period of 90 days. Adding a field is fine.
- Money fields are integers in cents and end in `_cents`.
- Pagination: `page` starts at 1, `per_page` defaults to 20 and is capped at 100. Lists are sorted by
  `created_at` descending with `id` as tiebreaker so that pages never overlap.
- Every query parameter is validated; invalid values return 400, never 500.
- Endpoints that return personal data (name, email) are limited to what the screen needs.
