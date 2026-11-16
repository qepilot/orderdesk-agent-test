# REST API conventions

- Prefix `/api/v1` (`restaurant.app.api.api_router`; add new endpoints to it).
- Error body, same for every status:
  `{"error": {"code", "message", "details"?, "request_id"}}`.
  Codes: `validation_error` (422, `details` = `[{field, message, type}]`), `not_found` (404),
  `conflict` (409), `bad_request` (400), `unauthorized` (401), `forbidden` (403),
  `method_not_allowed` (405), `internal_error` (500, generic message, never a trace or SQL).
  Services raise `NotFoundError`, `ConflictError`, `AppValidationError` or `AppError`.
- Pagination: `limit` (default 20, 1-100) and `offset` (>= 0). `limit` above 100 is
  **rejected with 422**, not clamped. Response: `{items, total, limit, offset}`; `total` is the
  count before paging. Use `Pagination` and `make_page`.
- `X-Request-ID`: a valid incoming id (8-64 chars of `A-Za-z0-9._-`) is kept, otherwise a UUID
  is generated. It is echoed in the response header and in every error body.
- OpenAPI docs at `/api/docs` (`/api/openapi.json`); disabled when `RESTAURANT_ENV=production`.
- CORS is off (no CORS middleware installed).
- Money fields are integer `*_cents`; timestamps are ISO-8601 UTC (`utc_iso`, e.g. `2026-01-02T03:04:05Z`).
