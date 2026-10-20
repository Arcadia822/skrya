# Source Health Architecture

The source health module provides topic-scoped health monitoring, automated failure tracking, and adaptive backoff for Skrya's information sources.
It tracks source reliability across digest runs, protects the orchestrator from repeated slow requests to persistently broken feeds, and enables honest operator diagnostics.

## Problem Statement

Historically, Skrya tracked sources via a static boolean flag (`enabled: true/false` in `sources.json`).
When an external RSS feed or search endpoint suffered transient downtime, rate limiting, or persistent breakage:

1. **Silent Failure**: Fetch errors were swallowed or skipped, providing no visibility into failing feeds.
2. **Resource Waste**: Persistently broken sources were queried on every digest run without backoff.
3. **No Automated Recovery**: Outages required manual inspection or configuration edits.
4. **Misleading Status**: Agents and operators could not distinguish between a temporary backoff and deliberate source deactivation.

## Core Design Principles

1. **Lazy Initialization and Zero-Write Previews**.
The `SourceHealthStore` constructor never creates directories or files on disk.
Read-only queries (`should_fetch`, `report`, `snapshot`) execute completely without side effects.
Digest previews remain strictly non-mutating.

2. **Schema Versioning and Unknown Field Preservation**.
Stored under `skrya.source-health.v1`.
All unknown top-level metadata and per-source fields are preserved through read-write cycles.
Future migrations can safely enrich the health payload without data loss.

3. **Atomic File Writes**.
Writes to `source-health.json` use process-isolated temporary files (`.source-health.json.tmp.<pid>.<timestamp>`),
flushed and synced via `os.fsync` before an atomic `os.replace`.
Torn writes from process interruption or concurrent readers cannot corrupt health state.

4. **Strict Boundary State Transitions**.
- `ok` $\to$ `degraded`: Exactly at consecutive failures $\ge 3$.
- `degraded` $\to$ `error`: Exactly at consecutive failures $\ge 10$.
- `degraded` $\to$ `ok`: Immediate on 1 successful fetch (consecutive failures reset to 0).
- `error` $\to$ `degraded`: After $\ge 24$ hours of backoff, the store allows 1 probe fetch; if successful, status transitions to `degraded`. Next success recovers to `ok`.

5. **Genuine UTC Clock and No Skipped-Attempt Penalties**.
All timestamps are recorded in genuine UTC ISO-8601 strings.
Skipped fetch attempts during backoff are read-only and never counted as failures.

6. **Credential Redaction**.
Failure reasons are sanitized before recording and again when loaded from disk, so previously persisted unsafe errors cannot bypass the corrected boundary:
Bearer tokens, HTTP Basic authentication credentials, Authorization headers (including non-Bearer values), sensitive headers such as `X-API-Key`, quoted and unquoted payload assignments (`"api_key": "..."`, `'password': '...'`, `password=...`), and sensitive URL query parameters are redacted.

7. **Display Name Separation and Truthful Reporting**.
The store accepts a `source_names: Mapping[str, str]` mapping configured by the parent orchestrator.
Diagnostics report configured human names rather than internal IDs.
Backed-off sources are explicitly reported as temporary backoff rather than falsely described as "disabled".
Health reports are maintained outside the exact-five-actions digest footer contract.

8. **Corrupt File Refusal**.
If `source-health.json` is malformed JSON, invalid UTF-8, structurally malformed (a non-dict `sources` container or a non-dict source entry), or unreadable, the store retains the original bytes in memory and reads as empty state.
`save()` raises `SourceHealthCorruptError` without writing anything until the file is repaired or deleted manually and a fresh store is constructed.
No automatic backup is created; deliberate repair is always a human decision.

## State File Location & Schema

### Location
```text
<skrya-data-root>/topics/<topic-id>/source-health.json
```

### Schema (`skrya.source-health.v1`)
```json
{
  "interface_version": "skrya.source-health.v1",
  "updated_at": "2026-10-20T10:00:00+00:00",
  "sources": {
    "the-verge": {
      "status": "ok",
      "last_success_at": "2026-10-20T09:30:00+00:00",
      "last_fetch_at": "2026-10-20T09:30:00+00:00",
      "consecutive_failures": 0,
      "last_error": null,
      "item_count": 5
    },
    "broken-feed": {
      "status": "error",
      "last_success_at": "2026-10-15T08:00:00+00:00",
      "last_fetch_at": "2026-10-20T09:30:00+00:00",
      "last_error_at": "2026-10-20T09:30:00+00:00",
      "consecutive_failures": 10,
      "last_error": "HTTP 403: Forbidden",
      "item_count": 0
    }
  }
}
```

## API Reference

### `SourceHealthStore`

```python
class SourceHealthStore:
    def __init__(
        self,
        topic_dir: Path | str,
        *,
        clock: Callable[[], datetime | float] | datetime | float | None = None,
        source_names: Mapping[str, str] | None = None,
    ) -> None: ...

    def should_fetch(self, source_id: str) -> bool: ...

    def record_success(self, source_id: str, item_count: int = 0) -> None: ...

    def record_failure(self, source_id: str, error: Any) -> None: ...

    def set_generation(self, source_id: str, generation: Any) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...

    def save(self) -> None: ...

    def get_source_display_name(self, source_id: str) -> str: ...

    def report(self, language: str = "zh-CN") -> str: ...
```

### Clock Convention

The `clock` parameter accepts:
- `None`: defaults to `datetime.now(timezone.utc)`.
- A callable `() -> datetime | float`: evaluated on each check/write.
- A fixed `datetime` (naive datetimes are treated as UTC; aware datetimes are converted to UTC).
- A fixed Unix timestamp (`int` or `float`).

### Corrupt File Refusal

`save()` raises `SourceHealthCorruptError` (a `RuntimeError` subclass) without mutating disk when the file loaded at construction was:

- Malformed JSON or a non-object JSON root.
- Invalid UTF-8.
- Structurally malformed: a non-dict `sources` container or a non-dict source entry.
- Unreadable (the file exists but cannot be read; unreadable is never treated as absent).

Read-only operations (`should_fetch`, `snapshot`, `report`) still work on the empty in-memory state. Recovery is deliberate: repair or delete the file manually, then construct a fresh store.

### Generation Mirror

`set_generation(source_id, generation)` stores the lifecycle generation into the entry's extra fields under `generation`.
The lifecycle collector calls it after a successful `EventLifecycle.record_source` and before `save`.
It never changes `status`, `consecutive_failures`, `item_count`, timestamps, or backoff behavior, and the value survives unknown-field preservation and save/reload round trips.
