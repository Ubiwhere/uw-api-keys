# Spec — Per-request cost of API key auth (issue #2)

Source: https://github.com/Ubiwhere/uw-api-keys/issues/2 (all five problems confirmed by reading
`f1fbaa0`). Scope agreed with the maintainer: **one PR, no schema migrations**.

Out of scope (follow-up issues): switching the stored hash to HMAC/SHA-256 (needs a hash
migration), an async/batched log writer hook, scrubbing credentials from existing log rows.

All new settings live under the existing `UW_API_KEYS_` prefix (`conf.py`).

## R1 — Validation cache (problem 1)

- Setting `VALIDATION_CACHE_TIMEOUT: int = 60` (seconds). `0` disables the cache.
- Setting `VALIDATION_CACHE_ALIAS: str = "default"` (Django cache alias).
- After a successful `get_key`, store under `uw_api_keys:v1:<sha256(full key string)>` the value
  `{"pk": <APIKey pk>, "hashed_key": <APIKey.hashed_key>}` with the configured timeout.
- On a cache hit: load the `APIKey` by pk. The hit is honoured only if the row exists and its
  `hashed_key`, `prefix` and `public_key` still match the presented key; otherwise fall through
  to the full `check_password` path. This makes rotation (`update_key`) and deletion
  self-invalidating without signals.
- Expiry (`expired`) is evaluated on every request, cached or not.
- Failed validations are never cached.

Success criteria:
- Two consecutive authenticated requests with the same key run the password hasher **once**.
- After `APIKey.objects.update_key(obj)` the old key is rejected even while its cache entry lives.
- After deleting the key, the old key is rejected.
- A key that expires after being cached is rejected.
- With `VALIDATION_CACHE_TIMEOUT = 0` the hasher runs on every request.

## R2 — Throttled `last_seen` (problem 2)

- Setting `LAST_SEEN_UPDATE_INTERVAL: int = 300` (seconds). `0` = update on every request.
- `last_seen` is written only when it is `NULL` or older than the interval, using
  `APIKey.objects.filter(pk=...).update(last_seen=now)` (single `UPDATE`, no `save()`).

Success criteria:
- First use sets `last_seen`.
- A second request inside the interval issues **no** `UPDATE` on the api key table.
- A request after the interval has elapsed updates `last_seen`.

## R3 — Usage log: redaction, META, retention (problem 3)

- Setting `LOG_REDACTED_HEADERS: list[str] = ["Authorization", "Proxy-Authorization", "Cookie"]`.
  Matching is case-insensitive on `request.headers`; the equivalent `META` keys
  (`HTTP_AUTHORIZATION`, `HTTP_PROXY_AUTHORIZATION`, `HTTP_COOKIE`) are redacted too.
- Redacted values are replaced with the literal `"[REDACTED]"` (key kept, so it is visible that
  the header was sent).
- The API key query parameter (`AUTH_HEADER_PREFIX`) is redacted inside `META["QUERY_STRING"]`
  (and `REQUEST_URI`/`RAW_URI` if present). `endpoint` is `request.path`, which carries no query
  string, so it needs no change.
- Setting `LOG_REQUEST_META: bool = True` (maintainer decision: keep current behaviour, with
  redaction). When false, `meta` is stored as `NULL`. README warns that under `runserver` META
  includes the process environment, which redaction does not cover.
- Setting `LOG_RETENTION_DAYS: int | None = None`.
- Management command `prune_api_key_logs [--days N] [--batch-size 10000]` deletes
  `APIKeyLogEvent` rows with `created_at` older than `--days` (or the setting), in batches by
  primary key. Neither given → `CommandError`. Prints the number of deleted rows.

Success criteria:
- A logged request authenticated via `Authorization: Api-Key <key>` stores no substring of the
  key anywhere in the log row (headers, meta, body, endpoint).
- Same with `ENABLE_QUERY_PARAM_AUTH = True` and `?Api-Key=<key>` with `LOG_REQUEST_META = True`.
- A `Cookie` header is stored as `"[REDACTED]"`.
- Default settings store a redacted `meta`; `LOG_REQUEST_META = False` stores `meta = NULL`.
- `prune_api_key_logs --days 30` removes rows older than 30 days and keeps newer ones.

## R4 — Scopes fetched once (problem 4)

- `APIKeyPermissions` loads the key's grants with one query
  (`(content_type_id, operation name)` pairs) and memoises them on the `APIKey` instance for the
  request; `has_object_permission` reuses them.
- Semantics unchanged: no scopes → allow all; scopes present → allow iff a scope for the view's
  model contains the current operation; a scope with no operations grants nothing.

Success criteria:
- Permission check for a scoped key issues at most **1** query, and `has_object_permission`
  after `has_permission` issues **0**.
- Existing semantics hold (allow-all, allowed op, denied op, other model denied).

## R5 — Log admin scales (problem 5)

- `show_full_result_count = False`.
- Paginator: on PostgreSQL, for an **unfiltered** queryset, `count` comes from
  `pg_class.reltuples` when that estimate is ≥ 0; otherwise (filtered, other vendors, or no
  stats yet) the real `COUNT(*)`.
- `list_filter = ["api_key"]`, `list_select_related = ["api_key"]`,
  `search_fields = ["api_key__name", "endpoint"]`, `ordering = ["-id"]`.

Success criteria:
- Changelist responds 200 and its query count does not grow with the number of rows shown.
- No query against the log table uses `DISTINCT`.
- `?q=<name>` responds 200 and filters by key name (today it raises).
- Unfiltered changelist on PostgreSQL issues no `COUNT(*)` over the log table.

## Test harness (new — the repo had none)

- `pytest` + `pytest-django`, test settings in `tests/settings.py`, a tiny test app with a DRF
  view over a model to exercise auth + permissions end to end through the test client.
- PostgreSQL 15 via `docker-compose.test.yml` on host port 55432; env vars override
  connection details.
- Password hashing in tests uses a counting hasher (a fake, registered via
  `PASSWORD_HASHERS`) so tests can observe how often verification runs.
