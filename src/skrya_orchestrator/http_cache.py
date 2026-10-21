from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import urllib.error
from urllib.request import Request, urlopen

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

TTL_RSS_HOT = 1800
TTL_RSS_WARM = 7200
TTL_RSSHUB = 600
TTL_TRANSLATION = 604800
TTL_RUNTIME_RETRIEVAL = 0

CLEANUP_GRACE_SECONDS = 86400

# .tmp.* files younger than this are treated as active writes by another
# concurrent request: cleanup/clear must skip such entries entirely.
ACTIVE_TMP_MAX_AGE_SECONDS = 3600

READ_CHUNK_SIZE = 65536


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _is_hex64(name: str) -> bool:
    if len(name) != 64:
        return False
    return all(c in "0123456789abcdef" for c in name.lower())


def _has_symlink_ancestor(path: Path) -> bool:
    return path.is_symlink() or any(
        parent.is_symlink() for parent in path.absolute().parents
    )


def _close_quietly(obj: Any) -> None:
    if obj is not None and hasattr(obj, "close"):
        try:
            obj.close()
        except Exception:
            pass


def default_ttl(source: dict[str, Any] | str, *, tier: str | None = None) -> int:
    """Select appropriate default TTL in seconds based on source type or explicit override.

    Supported defaults:
    - rss (hot): 1800 seconds (30 minutes)
    - rss (warm): 7200 seconds (2 hours)
    - rsshub: 600 seconds (10 minutes)
    - translation: 604800 seconds (7 days)
    - runtime-retrieval: 0 seconds (un-cached)
    """
    if source is None:
        raise ValueError("Source cannot be None")

    if isinstance(source, dict):
        if "ttl_seconds" in source:
            raw_override = source.get("ttl_seconds")
            if (
                raw_override is None
                or isinstance(raw_override, bool)
                or not isinstance(raw_override, (int, float))
            ):
                raise ValueError(f"Invalid ttl_seconds override: {raw_override!r}")
            ttl_int = int(raw_override)
            if ttl_int <= 0:
                raise ValueError(
                    f"Invalid ttl_seconds override: {raw_override!r}. Must be a positive integer."
                )
            return ttl_int

        source_type = source.get("type") or source.get("source_type") or ""
        if isinstance(source_type, str):
            source_type = source_type.strip().lower()
        else:
            source_type = ""

        raw_tier = tier if tier is not None else source.get("tier")
        resolved_tier = raw_tier.strip().lower() if isinstance(raw_tier, str) else ""

        if source_type == "runtime-retrieval":
            return TTL_RUNTIME_RETRIEVAL
        if source_type == "rsshub":
            return TTL_RSSHUB
        if source_type == "translation":
            return TTL_TRANSLATION
        if source_type in ("rss", ""):
            if resolved_tier == "warm":
                return TTL_RSS_WARM
            if resolved_tier in ("hot", ""):
                return TTL_RSS_HOT
            raise ValueError(f"Unsupported tier: {resolved_tier!r}")

        raise ValueError(f"Unsupported source type: {source_type!r}")

    if isinstance(source, str):
        normalized = source.strip().lower()
        resolved_tier = tier.strip().lower() if tier is not None else ""

        if normalized == "runtime-retrieval":
            return TTL_RUNTIME_RETRIEVAL
        if normalized == "rsshub":
            return TTL_RSSHUB
        if normalized == "translation":
            return TTL_TRANSLATION
        if normalized == "rss":
            if resolved_tier == "warm":
                return TTL_RSS_WARM
            if resolved_tier in ("hot", ""):
                return TTL_RSS_HOT
            raise ValueError(f"Unsupported tier: {resolved_tier!r}")

        raise ValueError(f"Unsupported source identifier: {source!r}")

    raise TypeError(f"source must be a str or dict, got {type(source).__name__}")


@dataclass(frozen=True)
class HttpCacheMetadata:
    url: str
    url_hash: str
    fetched_at: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    status: int
    ttl_seconds: int
    expires_at: str
    body_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "url_hash": self.url_hash,
            "fetched_at": self.fetched_at,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
            "status": self.status,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at,
            "body_digest": self.body_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HttpCacheMetadata:
        for key in ("url", "url_hash", "fetched_at", "expires_at", "body_digest"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f"Invalid cache metadata field: {key}")
        for key in ("status", "ttl_seconds"):
            if isinstance(data.get(key), bool) or not isinstance(data.get(key), int):
                raise ValueError(f"Invalid cache metadata field: {key}")
        if data["ttl_seconds"] <= 0:
            raise ValueError("Invalid cache metadata field: ttl_seconds")
        for key in ("etag", "last_modified", "content_type"):
            if data.get(key) is not None and not isinstance(data[key], str):
                raise ValueError(f"Invalid cache metadata field: {key}")
        return cls(
            url=data["url"],
            url_hash=data["url_hash"],
            fetched_at=data["fetched_at"],
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
            content_type=data.get("content_type"),
            status=data["status"],
            ttl_seconds=data["ttl_seconds"],
            expires_at=data["expires_at"],
            body_digest=data["body_digest"],
        )



def _get_header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    if hasattr(headers, "get"):
        val = headers.get(name)
        if val is not None:
            return str(val)
        val = headers.get(name.lower())
        if val is not None:
            return str(val)
        val = headers.get(name.title())
        if val is not None:
            return str(val)
    return None


class HttpCache:
    """HTTP response cache rooted at data_root/cache/http."""

    def __init__(
        self,
        data_root: Path | str,
        *,
        clock: Callable[[], datetime | float] | datetime | float | None = None,
        opener: Any = None,
    ) -> None:
        self._data_root = Path(data_root).resolve(strict=False)
        self._cache_dir = self._data_root / "cache" / "http"
        self._clock = clock
        self._opener = opener

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def _now(self) -> datetime:
        if self._clock is None:
            return datetime.now(timezone.utc)
        if callable(self._clock):
            val = self._clock()
        else:
            val = self._clock

        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=timezone.utc)
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc)
        raise TypeError(f"Unsupported clock value: {val!r}")

    def fetch(
        self,
        url: str,
        *,
        ttl_seconds: int = 1800,
        force_refresh: bool = False,
        write: bool = True,
        timeout: int | float = 20,
        headers: dict[str, str] | None = None,
        validate: Callable[[str], None] | None = None,
        deadline: float | None = None,
    ) -> str:
        """Fetch URL content with cache and conditional request support.

        Parameters:
        - url: target HTTP or HTTPS URL.
        - ttl_seconds: time-to-live in seconds. A value of 0 bypasses caching.
        - force_refresh: bypass cache and conditional headers entirely.
        - write: when False, performs read-only fetch with zero filesystem writes.
        - timeout: request timeout passed directly to opener.
        - headers: optional extra HTTP headers merged over defaults.
        - validate: optional callback invoked with the decoded body text before
          any cache write; raising rejects the response without persisting it.
        - deadline: optional time.monotonic() time point; once exceeded while
          reading the response body, raises TimeoutError and closes the connection.
        """
        if not url or not isinstance(url, str):
            raise ValueError(f"Invalid URL: {url!r}")

        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or ttl_seconds < 0
        ):
            raise ValueError(
                f"Invalid ttl_seconds: {ttl_seconds!r}. Must be a non-negative number."
            )
        ttl_seconds = int(ttl_seconds)

        url_str = url.strip()
        h = url_hash(url_str)
        now = self._now()

        cached_entry: tuple[HttpCacheMetadata, str] | None = None
        if not force_refresh and ttl_seconds > 0:
            cached_entry = self._read_entry(h, expected_url=url_str)

        if cached_entry is not None:
            meta, body = cached_entry
            if self._is_fresh(meta, now, ttl_seconds):
                return body

        use_conditional = (
            cached_entry is not None
            and not force_refresh
            and bool(cached_entry[0].etag or cached_entry[0].last_modified)
        )

        result_body = self._execute_fetch(
            url=url_str,
            url_hash_str=h,
            conditional_entry=cached_entry if use_conditional else None,
            ttl_seconds=ttl_seconds,
            write=write,
            timeout=timeout,
            headers=headers,
            now=now,
            validate=validate,
            deadline=deadline,
        )
        if write:
            self.cleanup(exclude_url_hash=h)
        return result_body

    def _is_fresh(self, meta: HttpCacheMetadata, now: datetime, ttl_seconds: int) -> bool:
        if not meta.expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(meta.expires_at.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at = expires_at.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return False
        if now >= expires_at:
            return False
        # A shared cache hit must also respect this request's TTL: the entry may
        # have been written by a different request with a longer TTL. When the
        # real fetch timestamp cannot be parsed (legacy metadata), fall back to
        # the expires_at-only judgment above.
        try:
            fetched_at = datetime.fromisoformat(meta.fetched_at.replace("Z", "+00:00"))
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            else:
                fetched_at = fetched_at.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return True
        return now < fetched_at + timedelta(seconds=ttl_seconds)

    def _read_metadata(
        self, hash_str: str, expected_url: str | None = None
    ) -> HttpCacheMetadata | None:
        entry_dir = self._cache_dir / hash_str
        if _has_symlink_ancestor(entry_dir) or not entry_dir.is_dir():
            return None

        meta_path = entry_dir / "meta.json"
        if meta_path.is_symlink() or not meta_path.is_file():
            return None

        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            meta = HttpCacheMetadata.from_dict(data)
            if meta.status != 200 or meta.url_hash != hash_str:
                return None
            if url_hash(meta.url) != hash_str:
                return None
            if expected_url is not None and meta.url != expected_url:
                return None
            if not _is_hex64(meta.body_digest):
                return None
            return meta
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
            return None

    def _read_entry(
        self, hash_str: str, expected_url: str | None = None
    ) -> tuple[HttpCacheMetadata, str] | None:
        meta = self._read_metadata(hash_str, expected_url=expected_url)
        if meta is None:
            return None
        body_path = self._cache_dir / hash_str / "response.xml"
        if body_path.is_symlink() or not body_path.is_file():
            return None

        try:
            with body_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                body = f.read()
            actual_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if actual_digest != meta.body_digest:
                return None
            return meta, body
        except OSError:
            return None


    def _open_request(self, req: Request, timeout: int | float) -> Any:
        if self._opener is not None:
            if hasattr(self._opener, "open"):
                return self._opener.open(req, timeout=timeout)
            return self._opener(req, timeout=timeout)
        return urlopen(req, timeout=timeout)

    def _execute_fetch(
        self,
        *,
        url: str,
        url_hash_str: str,
        conditional_entry: tuple[HttpCacheMetadata, str] | None,
        ttl_seconds: int,
        write: bool,
        timeout: int | float,
        headers: dict[str, str] | None,
        now: datetime,
        validate: Callable[[str], None] | None = None,
        deadline: float | None = None,
    ) -> str:
        req_headers = dict(DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        if conditional_entry is not None:
            cached_meta = conditional_entry[0]
            if cached_meta.etag and "If-None-Match" not in req_headers:
                req_headers["If-None-Match"] = cached_meta.etag
            if cached_meta.last_modified and "If-Modified-Since" not in req_headers:
                req_headers["If-Modified-Since"] = cached_meta.last_modified

        req = Request(url, headers=req_headers)
        resp = None
        try:
            try:
                resp = self._open_request(req, timeout=timeout)
                status = getattr(resp, "status", None) or getattr(resp, "code", None) or 200
                resp_headers = getattr(resp, "headers", None)
            except urllib.error.HTTPError as exc:
                if exc.code == 304 and conditional_entry is not None:
                    resp = exc
                    status = 304
                    resp_headers = getattr(exc, "headers", None) or getattr(exc, "hdrs", None)
                else:
                    _close_quietly(exc)
                    raise

            if status == 304 and conditional_entry is not None:
                cached_meta, cached_body = conditional_entry
                current_entry = self._read_entry(url_hash_str, expected_url=url)
                if current_entry is None or current_entry[1] != cached_body:
                    _close_quietly(resp)
                    resp = None
                    return self._execute_fetch(
                        url=url,
                        url_hash_str=url_hash_str,
                        conditional_entry=None,
                        ttl_seconds=ttl_seconds,
                        write=write,
                        timeout=timeout,
                        headers=headers,
                        now=now,
                        validate=validate,
                        deadline=deadline,
                    )

                if write and ttl_seconds > 0:
                    new_expires_at = now + timedelta(seconds=ttl_seconds)
                    new_etag = _get_header(resp_headers, "ETag") or cached_meta.etag
                    new_last_modified = (
                        _get_header(resp_headers, "Last-Modified") or cached_meta.last_modified
                    )
                    new_content_type = (
                        _get_header(resp_headers, "Content-Type") or cached_meta.content_type
                    )

                    refreshed_meta = HttpCacheMetadata(
                        url=url,
                        url_hash=url_hash_str,
                        fetched_at=now.isoformat(),
                        etag=new_etag,
                        last_modified=new_last_modified,
                        content_type=new_content_type,
                        status=200,
                        ttl_seconds=ttl_seconds,
                        expires_at=new_expires_at.isoformat(),
                        body_digest=cached_meta.body_digest,
                    )
                    self._atomic_write_meta(url_hash_str, refreshed_meta)

                return cached_body

            if status != 200:
                err = urllib.error.HTTPError(
                    url,
                    status,
                    f"HTTP error {status}",
                    getattr(resp, "headers", None) or {},
                    None,
                )
                raise err

            raw_body = self._read_body_chunks(resp, deadline=deadline)
            body_text = raw_body.decode("utf-8", errors="replace")

            if validate is not None:
                validate(body_text)

            if write and ttl_seconds > 0:
                self._save_response(
                    url=url,
                    url_hash_str=url_hash_str,
                    resp=resp,
                    body=body_text,
                    ttl_seconds=ttl_seconds,
                    now=now,
                )

            return body_text
        finally:
            _close_quietly(resp)

    def _read_body_chunks(self, resp: Any, *, deadline: float | None) -> bytes:
        """Read the response body in bounded chunks, honoring an optional deadline.

        A plain unbounded resp.read() can keep a connection open far past the
        request timeout, and resp.read(n) blocks until n bytes or EOF, so a
        server dribbling bytes below the socket timeout would stall it forever.
        With a deadline, each iteration uses resp.read1(), which returns as
        soon as any data is available, and checks time.monotonic() against the
        deadline before the next read; exceeding it raises TimeoutError (the
        caller's finally block closes the connection). Non-stream responses
        without read1 fall back to a single resp.read().
        """
        if deadline is None:
            return resp.read()
        chunks: list[bytes] = []
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("HTTP response body read exceeded deadline")
            try:
                chunk = resp.read1(READ_CHUNK_SIZE)
            except (AttributeError, TypeError):
                chunk = resp.read()
                if chunk:
                    chunks.append(chunk)
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def _save_response(
        self,
        *,
        url: str,
        url_hash_str: str,
        resp: Any,
        body: str,
        ttl_seconds: int,
        now: datetime,
    ) -> None:
        headers = getattr(resp, "headers", None)
        etag = _get_header(headers, "ETag")
        last_modified = _get_header(headers, "Last-Modified")
        content_type = _get_header(headers, "Content-Type")

        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        expires_at = now + timedelta(seconds=ttl_seconds)

        meta = HttpCacheMetadata(
            url=url,
            url_hash=url_hash_str,
            fetched_at=now.isoformat(),
            etag=etag,
            last_modified=last_modified,
            content_type=content_type,
            status=200,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at.isoformat(),
            body_digest=body_sha,
        )
        self._atomic_write_entry(url_hash_str, meta, body)

    def _atomic_write_entry(
        self,
        url_hash_str: str,
        meta: HttpCacheMetadata,
        body: str,
    ) -> None:
        entry_dir = self._cache_dir / url_hash_str
        if _has_symlink_ancestor(entry_dir):
            return
        entry_dir.mkdir(parents=True, exist_ok=True)
        if _has_symlink_ancestor(entry_dir):
            return

        tmp_response = entry_dir / f".tmp.response.{os.getpid()}.{time.time_ns()}.xml"
        tmp_meta = entry_dir / f".tmp.meta.{os.getpid()}.{time.time_ns()}.json"

        try:
            with tmp_response.open("w", encoding="utf-8", newline="") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())

            with tmp_meta.open("w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_response, entry_dir / "response.xml")
            os.replace(tmp_meta, entry_dir / "meta.json")
        finally:
            if tmp_response.exists():
                try:
                    tmp_response.unlink()
                except OSError:
                    pass
            if tmp_meta.exists():
                try:
                    tmp_meta.unlink()
                except OSError:
                    pass


    def _atomic_write_meta(self, url_hash_str: str, meta: HttpCacheMetadata) -> None:
        entry_dir = self._cache_dir / url_hash_str
        if _has_symlink_ancestor(entry_dir) or not entry_dir.is_dir():
            return

        tmp_meta = entry_dir / f".tmp.meta.{os.getpid()}.{time.time_ns()}.json"
        try:
            with tmp_meta.open("w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_meta, entry_dir / "meta.json")
        finally:
            if tmp_meta.exists():
                try:
                    tmp_meta.unlink()
                except OSError:
                    pass

    def _tmp_file_age(self, child: Path, now: datetime) -> timedelta | None:
        try:
            mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None
        return now - mtime

    def _remove_entry_dir(self, entry_dir: Path) -> bool:
        if _has_symlink_ancestor(entry_dir) or not entry_dir.is_dir():
            return False

        now = self._now()
        active_tmp_age = timedelta(seconds=ACTIVE_TMP_MAX_AGE_SECONDS)

        # Distinguish active tmp files from leftovers: when an entry holds a
        # recent .tmp.* file another request may be mid-write, so the whole
        # entry is left untouched. Only older leftovers are removed below.
        for child in entry_dir.iterdir():
            if not (child.is_file() and not child.is_symlink() and child.name.startswith(".tmp.")):
                continue
            age = self._tmp_file_age(child, now)
            if age is None or age < active_tmp_age:
                return False

        meta_path = entry_dir / "meta.json"
        body_path = entry_dir / "response.xml"
        removed_any = False

        if meta_path.is_file() and not meta_path.is_symlink():
            try:
                meta_path.unlink()
                removed_any = True
            except OSError:
                pass

        if body_path.is_file() and not body_path.is_symlink():
            try:
                body_path.unlink()
                removed_any = True
            except OSError:
                pass

        for child in entry_dir.iterdir():
            if (
                child.is_file()
                and not child.is_symlink()
                and child.name.startswith(".tmp.")
            ):
                age = self._tmp_file_age(child, now)
                if age is not None and age < active_tmp_age:
                    continue
                try:
                    child.unlink()
                except OSError:
                    pass

        try:
            entry_dir.rmdir()
        except OSError:
            pass

        return removed_any

    def cleanup(self, *, exclude_url_hash: str | None = None) -> int:
        """Remove owned entries expired beyond the 24-hour grace window.

        Entries with recent .tmp.* files (active writes by concurrent requests)
        are skipped entirely; only leftover tmp files older than
        ACTIVE_TMP_MAX_AGE_SECONDS are removed.
        """
        if _has_symlink_ancestor(self._cache_dir) or not self._cache_dir.is_dir():
            return 0

        now = self._now()
        grace = timedelta(seconds=CLEANUP_GRACE_SECONDS)
        removed_count = 0

        for entry_dir in list(self._cache_dir.iterdir()):
            if not _is_hex64(entry_dir.name):
                continue
            if exclude_url_hash and entry_dir.name == exclude_url_hash:
                continue
            meta = self._read_metadata(entry_dir.name)
            if meta is None:
                continue

            try:
                expires_at = datetime.fromisoformat(meta.expires_at.replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                else:
                    expires_at = expires_at.astimezone(timezone.utc)

                if now - expires_at >= grace:
                    if self._remove_entry_dir(entry_dir):
                        removed_count += 1
            except (OSError, ValueError):
                continue

        return removed_count

    def clear(self) -> int:
        if _has_symlink_ancestor(self._cache_dir) or not self._cache_dir.is_dir():
            return 0

        count = 0
        for entry_dir in list(self._cache_dir.iterdir()):
            if not _is_hex64(entry_dir.name):
                continue
            if self._read_metadata(entry_dir.name) is None:
                continue
            if self._remove_entry_dir(entry_dir):
                count += 1

        return count


    def get_metadata(self, url: str) -> HttpCacheMetadata | None:
        h = url_hash(url.strip())
        entry = self._read_entry(h, expected_url=url.strip())
        if entry is None:
            return None
        return entry[0]
