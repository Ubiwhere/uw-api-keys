# PLAN — fix-2-api-key-per-request-cost

Spec: `dev_docs/specs/fix-2-api-key-per-request-cost.md` · Issue: Ubiwhere/uw-api-keys#2 ·
Red: 19 failing tests in `tests/` (verified at `f1fbaa0`).

## 1. Overview

Make API key authentication cheap per request without touching the schema. Today each request
runs PBKDF2 (`APIKey.is_valid` → `check_password`), saves `last_seen`, issues two scope queries
(`scopes.count()` + `exists()`, twice when object permissions run), and — when logging is on —
inserts a log row that contains the API key in `headers`/`META`/`QUERY_STRING`. The log admin
issues a full `COUNT(*)`, a `DISTINCT` over the log table for the filter sidebar, one query per
row for `api_key`, and crashes on search. This step fixes all five without migrations: a
self-validating cache in front of the hasher, a throttled single-statement `last_seen` update,
redacted logging (META optional) plus a prune command, one memoised scope query, and admin
settings with an estimated-count paginator.

## 2. Files to create or modify

Settings
- `src/uw_api_keys/conf.py` — new settings (R1, R2, R3).

Auth path
- `src/uw_api_keys/models.py` — cache-aware `APIKeyManager.get_key`, throttled
  `APIKey.update_last_seen`, `APIKey.scope_grants()` memoised.
- `src/uw_api_keys/backends.py` — redacted log payload; permissions use `scope_grants()`.
- `src/uw_api_keys/utils.py` — pure redaction helpers.

Retention
- `src/uw_api_keys/management/__init__.py`, `src/uw_api_keys/management/commands/__init__.py` —
  packages.
- `src/uw_api_keys/management/commands/prune_api_key_logs.py` — the prune command.

Admin
- `src/uw_api_keys/admin.py` — `APIKeyLogEventAdmin` settings + paginator.
- `src/uw_api_keys/paginators.py` — `EstimatedCountPaginator`.

Docs
- `README.md` — document the new settings, the `LOG_REQUEST_META` runserver caveat, the prune
  command, and the note for existing deployments (stored keys in old rows; rotate).

No test files change except where section 5 says so.

## 3. Detailed design per file

### `conf.py`
Add to `Conf`:
```python
VALIDATION_CACHE_TIMEOUT: int = 60          # seconds; 0 disables
VALIDATION_CACHE_ALIAS: str = "default"
LAST_SEEN_UPDATE_INTERVAL: int = 300        # seconds; 0 = every request
LOG_REDACTED_HEADERS: list[str] = ["Authorization", "Proxy-Authorization", "Cookie"]
LOG_REQUEST_META: bool = True               # maintainer decision; README warns about runserver env
LOG_RETENTION_DAYS: int | None = None
```

### `models.py`
- Module constants: `_CACHE_KEY_TEMPLATE = "uw_api_keys:v1:{digest}"`.
- `def _validation_cache_key(key: str) -> str` — `sha256(key.encode()).hexdigest()` into the
  template.
- `APIKeyManager.get_key(self, key: str) -> APIKey | None` — new flow:
  1. split into `prefix, public, private` (unchanged; `None` on `ValueError`).
  2. `api_key = self._get_cached(key, prefix, public)`; if found and not `expired` →
     `update_last_seen()`; return it.
  3. else current path: `get(prefix=, public_key=)`, `expired` check, `is_valid(private)`.
  4. on success → `self._set_cached(key, api_key)`, `update_last_seen()`, return.
  Use `self.get_queryset()`/`APIKey.objects` consistently (the backend instantiates
  `APIKeyManager()` unbound, so keep using `APIKey.objects` inside).
- `_get_cached(self, key, prefix, public) -> APIKey | None` — returns `None` when
  `VALIDATION_CACHE_TIMEOUT <= 0`, on miss, if the pk row is gone, or if
  `(row.prefix, row.public_key, row.hashed_key) != (prefix, public, cached["hashed_key"])`.
  The hashed_key comparison is what makes rotation self-invalidating.
- `_set_cached(self, key, api_key) -> None` — `caches[alias].set(cache_key,
  {"pk": api_key.pk, "hashed_key": api_key.hashed_key}, timeout)`; no-op when timeout ≤ 0.
  Never called on failure.
- `APIKey.update_last_seen(self) -> None` — `now = timezone.now()`; skip if
  `interval > 0 and self.last_seen and now - self.last_seen < timedelta(seconds=interval)`;
  else `APIKey.objects.filter(pk=self.pk).update(last_seen=now)` and set `self.last_seen = now`.
- `APIKey.scope_grants(self) -> frozenset[tuple[int, str | None]]` — memoised on
  `self._scope_grants`:
  `frozenset(APIKeyScope.objects.filter(api_key=self).values_list("content_type_id",
  "operations__name"))`. LEFT JOIN means a scope with no operations yields `(ct_id, None)`, so
  the set is non-empty (key is scoped) yet grants nothing — preserves current semantics.

### `utils.py`
- `REDACTED = "[REDACTED]"`.
- `redact_headers(headers: Mapping[str, Any], names: Iterable[str]) -> dict` — case-insensitive
  match on header name; keeps the key, replaces value.
- `redact_meta(meta: Mapping[str, Any], names: Iterable[str], query_param: str) -> dict` — maps
  each header name to its META key (`"HTTP_" + name.upper().replace("-", "_")`) and redacts it;
  for `QUERY_STRING`, `REQUEST_URI`, `RAW_URI` rewrites the value of `query_param` via
  `re.sub(rf"(^|[?&]){re.escape(param)}=[^&]*", rf"\1{param}=[REDACTED]", value)`.
  Note: Django's `request.headers` already strips the `HTTP_` prefix, so header names are
  `Authorization` etc.

### `backends.py`
- `authenticate_credentials`: build `headers = redact_headers({jsonable headers},
  LOG_REDACTED_HEADERS)`; `meta = redact_meta({jsonable META}, LOG_REDACTED_HEADERS,
  AUTH_HEADER_PREFIX) if LOG_REQUEST_META else None`. Body logic unchanged. Settings read
  through `uw_api_keys_settings` at call time (not cached at import), so the test `conf` fixture
  and runtime overrides work.
- `APIKeyPermissions.has_permission`: replace `count()`/`filter().exists()` with
  ```python
  grants = api_key.scope_grants()
  if not grants: return True
  ct_id = ContentType.objects.get_for_model(model).pk   # Django-cached, no query after first
  allowed = (ct_id, current_operation) in grants
  ```
  `has_object_permission` unchanged (delegates) — memoisation gives it zero queries because
  DRF passes the same `request.user.api_key` instance.

### `management/commands/prune_api_key_logs.py`
`class Command(BaseCommand)`:
- args: `--days` (int, ≥ 1), `--batch-size` (int, default 10000, ≥ 1).
- `days = options["days"] or uw_api_keys_settings.LOG_RETENTION_DAYS`; if `None` →
  `CommandError("No retention given: pass --days or set UW_API_KEYS_LOG_RETENTION_DAYS.")`
  (contains "days", as the red test expects).
- loop: `ids = list(qs.filter(created_at__lt=cutoff).order_by("pk").values_list("pk",
  flat=True)[:batch])`; `APIKeyLogEvent.objects.filter(pk__in=ids).delete()`; accumulate; stop
  when `ids` empty. Write `"Deleted {n} API key log events older than {days} days."`.
- Plain `.delete()`: the model has no dependents, so Django issues a single
  `DELETE ... WHERE id IN (...)` per batch (no collector fan-out).

### `paginators.py`
`class EstimatedCountPaginator(Paginator)` with `@cached_property count`:
- if `connection.vendor == "postgresql"` and `not self.object_list.query.where` → run
  `SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass` with
  `self.object_list.model._meta.db_table` (parameterised); return it if `>= 0`.
- otherwise `super().count`.
Uses `connections[self.object_list.db]`.

### `admin.py` — `APIKeyLogEventAdmin`
```python
search_fields = ["api_key__name", "endpoint"]
list_display = ["api_key", "endpoint", "created_at"]
list_filter = ["api_key"]
list_select_related = ["api_key"]
show_full_result_count = False
paginator = EstimatedCountPaginator
ordering = ["-id"]
```
No `date_hierarchy` (it is absent today; keep it so).

## 4. Configuration

Settings above (all `UW_API_KEYS_*`). Uses an existing Django cache alias (`default`); projects
with `DummyCache` simply get no caching. Test harness: `docker compose -f
docker-compose.test.yml up -d`, then `.venv/bin/pytest`.

## 5. Tests

All are integration (real Postgres, DRF test client / admin client). Existing red tests stay
**unchanged**; they are the acceptance gate.

| File | Tests | Prio |
|---|---|---|
| `test_validation_cache.py` | verify-once (red), rotation, deletion, expiry-after-cache, disabled, failed-not-cached | p0 |
| `test_last_seen.py` | first-use, no UPDATE in interval (red), after interval, interval 0 | p0 |
| `test_usage_log.py` | key not stored [meta on/off] (red), query-param key not stored (red), cookie redacted (red), auth header redacted keeps name (red), meta NULL when disabled (red — renamed, see below), meta stored when enabled | p0 |
| `test_prune_logs.py` | older-than-days (red), batch size 1 (red), setting fallback (red), neither → error mentions days (red) | p1 |
| `test_permissions.py` | ≤1 query scoped (red), 0 queries object-perm after perm (red) | p1 |
| `test_admin_logs.py` | constant query count (red), no DISTINCT (red), search by name (red), filter by `api_key` (red), no COUNT unfiltered (red), exact count filtered | p1 |
| `test_auth_regression.py` | 9 semantic guards | p0 |

New tests to add in green (gaps found while planning):
- `test_usage_log.py::test_should_redact_custom_header_from_setting` — `conf(LOG_REDACTED_HEADERS=["X-Secret"])` → `headers["X-Secret"] == "[REDACTED]"` and `HTTP_X_SECRET` redacted in meta. p1.
- `test_validation_cache.py::test_should_reject_wrong_private_key_for_cached_public_key` — cache a valid key, then present same prefix/public with a different private part → 401. p0 (guards against a cache key that ignores the private part).

## 6. Dependencies

None at runtime. Test extra already added in red step (`pytest`, `pytest-django`, `psycopg`).

Changed red test (maintainer decision on `LOG_REQUEST_META` default = `True`):
`test_should_store_null_meta_by_default` encoded the wrong expectation. It becomes
`test_should_store_null_meta_when_log_request_meta_disabled` (sets `conf(LOG_REQUEST_META=False)`,
asserts `meta is None`) plus `test_should_store_redacted_meta_by_default` (no conf; asserts
`meta["HTTP_AUTHORIZATION"] == "[REDACTED]"`).

Version: bump `pyproject.toml` to `0.1.0` (approved).

## 7. Decisions / open questions

1. `LOG_REQUEST_META` defaults to `True` — decided by maintainer.
2. **Cache stores the PBKDF2 `hashed_key`** in the Django cache. It is the same value already in
   the DB and is only compared, never used to verify; acceptable. Alternative: store
   `sha256(hashed_key)` — trivial if preferred.
3. Version bump to `0.1.0` — approved.
