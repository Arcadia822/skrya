# HTTP Cache Architecture

The HTTP cache module provides disk-backed HTTP response caching for Skrya.
Fresh cache hits reuse feed responses without a network request.
Expired entries use HTTP validators when available.

## Problem Statement

Before this module, Skrya executed unconditional HTTP fetches during every digest run.
Each run refetched every RSS feed and external source even if contents had not changed.
Network roundtrips consumed bandwidth and delayed digest generation.
In addition, public RSS endpoints and RSSHub instances risked being rate limited.

## Core Design Principles

1. Isolated filesystem subtree.
All cache artifacts live strictly under `<data_root>/cache/http/`.
No other files or directories are touched.

2. Lazy constructor.
Initializing `HttpCache` creates no directories on disk.
Directories are materialized only upon the first write operation.

3. Byte-for-byte read-only mode.
When `write=False`, the cache performs zero filesystem writes.
It never creates directories, updates metadata, or triggers cleanup.
Digest previews remain completely side-effect-free.

4. Process-isolated temporary writes and atomic replace.
Cache responses and metadata are written to unique process-isolated temporary files.
Each file is flushed and synced with `os.fsync` before being moved into place with `os.replace`.
Because response bodies and metadata are written in separate filesystem operations, they do not form a single transactional pair; instead, content digest verification guarantees that any torn or mismatched write pair is safely detected and treated as a cache miss rather than serving corrupted data.

5. Content digest and metadata verification.
Metadata stores the SHA-256 digest of the response body in `body_digest`.
Readers verify the body digest and metadata attributes (status must be 200, matching URL and url_hash) before returning cached content.
Mismatched or truncated files and entries with bad metadata/status are rejected as cache misses.

6. Standards-compliant HTTP conditional validation.
Expired entries send `If-None-Match` and `If-Modified-Since` headers.
An HTTP 304 Not Modified response reuses the verified cached body and refreshes expiry.
The implementation supports both real `urllib.error.HTTPError` 304 and custom opener responses.

7. Fail-safe error propagation and resource closure.
Network failures and non-200 HTTP statuses propagate immediately without caching (only complete successful 200 representations are cached; partial 206 responses are rejected).
Every response and error body is closed upon completion in a `finally` block to prevent socket or file descriptor leaks.
Errors are never cached as successes, and stale responses are never silently returned in place of failed network requests.

8. Safe cleanup and validator preservation.
Automatic cleanup retains expired entries for a 24-hour grace window to preserve conditional request validators.
Cleanup and clear operations are strictly restricted to recognized 64-hex URL directories containing matching owned metadata or response files; unknown and manual files/directories are preserved, and symlinks outside the cache are never traversed or deleted.

## Cache Directory Layout

```text
<data_root>/cache/http/
  <url-sha256>/
    response.xml       # Cached response body text
    meta.json          # Cache envelope and HTTP validator metadata
```

Each cache entry is identified by the 64-character SHA-256 hex digest of the normalized URL.

### Metadata Schema (`meta.json`)

```json
{
  "url": "https://example.com/rss.xml",
  "url_hash": "a1b2c3d4...",
  "fetched_at": "2026-10-20T10:00:00+00:00",
  "etag": "\"12345678\"",
  "last_modified": "Mon, 20 Oct 2026 09:30:00 GMT",
  "content_type": "application/rss+xml",
  "status": 200,
  "ttl_seconds": 1800,
  "expires_at": "2026-10-20T10:30:00+00:00",
  "body_digest": "e3b0c442..."
}
```

## API Reference

### `HttpCache`

```python
class HttpCache:
    def __init__(
        self,
        data_root: Path | str,
        *,
        clock: Callable[[], datetime | float] | datetime | float | None = None,
        opener: Any = None,
    ) -> None: ...

    def fetch(
        self,
        url: str,
        *,
        ttl_seconds: int = 1800,
        force_refresh: bool = False,
        write: bool = True,
        timeout: int | float = 20,
        headers: dict[str, str] | None = None,
    ) -> str: ...

    def cleanup(self, *, exclude_url_hash: str | None = None) -> int: ...

    def clear(self) -> int: ...

    def get_metadata(self, url: str) -> HttpCacheMetadata | None: ...
```

### `default_ttl`

```python
def default_ttl(source: dict[str, Any] | str, *, tier: str | None = None) -> int: ...
```

The `default_ttl` helper resolves recommended cache TTLs by source tier:
- `rss` (hot): 1800 seconds (30 minutes)
- `rss` (warm): 7200 seconds (2 hours)
- `rsshub`: 600 seconds (10 minutes)
- `translation`: 604800 seconds (7 days)
- `runtime-retrieval`: 0 seconds (un-cached)

Explicit per-source `ttl_seconds` overrides are respected.
Invalid TTL values less than or equal to zero or non-numeric types raise `ValueError`.

## Behavioral Matrix

| Scenario | Cache State | Network Action | Disk Action | Returned Value |
|---|---|---|---|---|
| Fresh hit | `now < expires_at` | None | None | Cached body |
| Expired hit (304) | `now >= expires_at` | Conditional GET | Atomically update `meta.json` | Cached body |
| Expired hit (200) | `now >= expires_at` | Conditional GET | Atomically update response and meta | New network body |
| Cache miss | None | Unconditional GET | Atomically write response and meta | New network body |
| Force refresh | Any | Unconditional GET | Atomically overwrite response and meta | New network body |
| Network failure | Any | Failed request | None | Raises exception |
| Readonly preview | Any | Normal evaluation | None | Evaluated body |
| Zero TTL | Any | Unconditional GET | None | New network body |

## Lifecycle and Cleanup

The cache implements a 24-hour grace window for expired entries.
When an entry expires, its ETag and Last-Modified validators remain valuable for future conditional requests.
Deleting an entry immediately at expiration forces a full body download on the next run.
Therefore, `cleanup()` only removes entries whose `expires_at` is older than 24 hours.
During fetch execution, the current URL's directory is excluded from immediate cleanup.
Validators for the active request are never deleted before the request is attempted.

Both `cleanup()` and `clear()` restrict modifications to recognized 64-character hex directories matching owned cache entries. Manual files, custom subdirectories, and symlink directories outside the cache are strictly preserved.

## CLI integration

The `cache` subcommand in `main.py` maintains the HTTP cache without needing any topic or runs data:

```bash
skrya cache --root <workspace> --data-root <data-root> --clear-http-cache
skrya cache --root <workspace> --data-root <data-root> --cleanup-expired
```

- `--clear-http-cache` calls `HttpCache(data_root).clear()` and reports the number of removed entries.
- `--cleanup-expired` calls `HttpCache(data_root).cleanup()` and removes only entries past the 24-hour grace window.
- With no action flag the command returns exit code 2, reports usage, and changes no files.
- `--translation-language` is valid only with `--clear-translation-cache`, not with HTTP-only maintenance.
- Both actions touch only recognized cache entries under `<data_root>/cache/http/`.

`digest --force-refresh` propagates `force_refresh=True` through `IntelligenceService.generate_digest`, so live source collection bypasses HTTP cache freshness on demand. `digest --preview` keeps passing `write=False`, and the data root stays byte-for-byte unchanged.

## Translation cache interaction

Translation content-hash caching operates at the text translation layer (`docs/translation-cache.md`).
`HttpCache` operates at the transport layer for HTTP sources.
The default translation path uses the non-expiring translation cache, not an additional HTTP transport cache.
The `translation` TTL helper is available for generic HTTP callers.
