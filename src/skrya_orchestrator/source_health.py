from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_VERSION = "skrya.source-health.v1"
BACKOFF_WINDOW = timedelta(hours=24)
DEGRADED_THRESHOLD = 3
ERROR_THRESHOLD = 10


class SourceHealthCorruptError(RuntimeError):
    """Raised by SourceHealthStore.save() when the on-disk health file is corrupt or unreadable."""


# Keys that identify potential secrets or sensitive parameters in queries/headers/payloads
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(key|token|secret|auth|password|passwd|api[_-]?key|bearer|credential|signature|sig|access[_-]?token)"
)

_SENSITIVE_KEY_NAMES = r"(?:(?:x[\-_])?api[\-_]?key|access[\-_]?token|authorization|auth|token|secret|password|passwd|passphrase|credential[s]?|signature|sig)"

# Common credential shapes in error strings: bearer/basic tokens, URL queries and userinfo,
# quoted JSON/payload assignments, unquoted header and payload assignments.
_SECRET_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.~+/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)basic\s+[A-Za-z0-9_\-\.~+/]+=*"), "Basic [REDACTED]"),
    # Authorization schemes can contain quoted, comma-separated credentials.
    (
        re.compile(r"""(?i)\b(authorization)['"]?\s*[:=]\s*[^\r\n]*"""),
        r"\1: [REDACTED]",
    ),
    (re.compile(r"([?&](?:api_key|apikey|key|token|access_token|secret|signature|sig)=)[^& \t\n\r]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"://([^:@\s]+):([^@\s]+)@"), r"://\1:[REDACTED]@"),
    (re.compile(rf"(?i)(['\"])({_SENSITIVE_KEY_NAMES})\1\s*:\s*(['\"])[^'\"]*\3"), r"\1\2\1: \3[REDACTED]\3"),
    (re.compile(rf"(?i)\b({_SENSITIVE_KEY_NAMES})\s*:\s*(?!\[REDACTED\]|bearer\b|basic\b)[^\s,;]+"), r"\1: [REDACTED]"),
    (re.compile(rf"(?i)\b({_SENSITIVE_KEY_NAMES})\s*=\s*(?!\[REDACTED\]|%5bredacted%5d)[^&\s,;'\"<>]+"), r"\1=[REDACTED]"),
)


def redact_error(error: Any) -> str:
    """Produce a safe, concise, redacted error message without credentials or secrets."""
    if error is None:
        return ""
    text = str(error).strip()
    if not text:
        return ""

    # Redact known credential patterns
    for pattern, replacement in _SECRET_REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)

    # Redact embedded URLs if they contain sensitive query params
    def _sanitize_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        try:
            parts = urlsplit(raw_url)
            if not parts.scheme or not parts.netloc:
                return raw_url
            # Clean netloc userinfo
            netloc = parts.netloc
            if "@" in netloc:
                userinfo, host = netloc.rsplit("@", 1)
                if ":" in userinfo:
                    u, _ = userinfo.split(":", 1)
                    netloc = f"{u}:[REDACTED]@{host}"
                else:
                    netloc = f"[REDACTED]@{host}"

            # Clean query parameters
            query_pairs = parse_qsl(parts.query, keep_blank_values=True)
            if query_pairs:
                cleaned_pairs: list[tuple[str, str]] = []
                for k, v in query_pairs:
                    if _SENSITIVE_KEY_PATTERN.search(k):
                        cleaned_pairs.append((k, "[REDACTED]"))
                    else:
                        cleaned_pairs.append((k, v))
                new_query = urlencode(cleaned_pairs)
            else:
                new_query = parts.query

            return urlunsplit((parts.scheme, netloc, parts.path, new_query, parts.fragment))
        except Exception:
            return raw_url

    text = re.sub(r"https?://\S+", _sanitize_url, text)

    # Truncate overly long error messages to a concise single line (e.g. 200 chars)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else text
    if len(first_line) > 200:
        first_line = first_line[:197] + "..."
    return first_line


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    # Handle 'Z' if Python < 3.11 compatibility is ever needed
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _format_iso_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


@dataclass(slots=True)
class SourceHealthEntry:
    status: str  # "ok" | "degraded" | "error"
    last_success_at: str | None
    last_fetch_at: str | None
    consecutive_failures: int
    last_error: str | None
    item_count: int
    last_error_at: str | None = None
    extra_fields: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.extra_fields:
            result.update(self.extra_fields)
        result.update(
            {
                "status": self.status,
                "last_success_at": self.last_success_at,
                "last_fetch_at": self.last_fetch_at,
                "consecutive_failures": self.consecutive_failures,
                "last_error": self.last_error,
                "item_count": self.item_count,
            }
        )
        if self.last_error_at is not None:
            result["last_error_at"] = self.last_error_at
        return result


@dataclass(slots=True)
class _LoadedState:
    """Parsed on-disk health state; corrupt_content is set instead of raising."""

    interface_version: str
    updated_at: str | None
    top_level_extra: dict[str, Any]
    sources: dict[str, SourceHealthEntry]
    corrupt_content: bytes | None


class SourceHealthStore:
    """Topic-scoped source health monitoring and automated backoff tracking.

    Guarantees:
    - Constructor never creates files or directories on disk.
    - Loads existing source-health.json if present; corrupt or unreadable content blocks save via SourceHealthCorruptError until manually repaired.
    - Preserves unknown top-level and per-source fields across writes.
    - Read-only operations (should_fetch, report, snapshot) never mutate disk.
    - Saves are atomic via process-isolated temp files and os.replace.
    - save() replays this store's recorded outcomes onto the freshest on-disk
      state under a file lock, so overlapping stores never drop each other's
      outcomes instead of a last-writer-wins whole-file overwrite.
    - Uses genuine UTC times throughout.
    """

    def __init__(
        self,
        topic_dir: Path | str,
        *,
        clock: Callable[[], datetime | float] | datetime | float | None = None,
        source_names: Mapping[str, str] | None = None,
    ) -> None:
        topic_path = Path(topic_dir).absolute()
        if topic_path.is_symlink() or topic_path.parent.is_symlink():
            raise SourceHealthCorruptError(f"refusing linked topic directory: {topic_path}")
        self._topic_dir = topic_path.parent.resolve(strict=False) / topic_path.name
        self._file_path = self._topic_dir / "source-health.json"
        self._clock = clock
        self._source_names: Mapping[str, str] = dict(source_names) if source_names is not None else {}

        # Raw in-memory state
        self._interface_version = SCHEMA_VERSION
        self._top_level_extra: dict[str, Any] = {}
        self._sources: dict[str, SourceHealthEntry] = {}
        self._updated_at: str | None = None
        self._corrupt_content: bytes | None = None
        # Outcomes recorded since load/save; replayed onto fresh disk state on save.
        self._pending_ops: list[tuple[Any, ...]] = []

        self._load()

    @property
    def topic_dir(self) -> Path:
        return self._topic_dir

    @property
    def file_path(self) -> Path:
        return self._file_path

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

    @staticmethod
    def _read_state(file_path: Path) -> _LoadedState:
        """Parse on-disk health state without mutating anything.

        A missing file loads as empty state; unreadable or malformed content is
        returned as corrupt_content so callers refuse to overwrite it.
        """
        empty = _LoadedState(SCHEMA_VERSION, None, {}, {}, None)
        if file_path.is_symlink() or any(parent.is_symlink() for parent in file_path.parents):
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, b"")
        if not file_path.is_file():
            return empty

        try:
            raw_bytes = file_path.read_bytes()
        except FileNotFoundError:
            return empty
        except OSError:
            # Unreadable is not the same as absent; block save until repaired
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, b"")

        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, raw_bytes)

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, raw_bytes)

        if not isinstance(payload, dict):
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, raw_bytes)

        sources_data = payload.get("sources")
        # Missing or null sources containers are malformed, not empty: {} and
        # {"sources": null} must mark corrupt and refuse saves like other bad shapes.
        if not isinstance(sources_data, dict) or any(
            not isinstance(entry, dict) for entry in sources_data.values()
        ):
            return _LoadedState(SCHEMA_VERSION, None, {}, {}, raw_bytes)

        interface_version = str(payload.get("interface_version") or SCHEMA_VERSION)
        updated_at = payload.get("updated_at")

        known_top_keys = {"interface_version", "updated_at", "sources"}
        top_level_extra = {k: v for k, v in payload.items() if k not in known_top_keys}

        sources: dict[str, SourceHealthEntry] = {}
        for source_id, s_data in sources_data.items():
            known_s_keys = {
                "status",
                "last_success_at",
                "last_fetch_at",
                "consecutive_failures",
                "last_error",
                "item_count",
                "last_error_at",
            }
            extra = {k: v for k, v in s_data.items() if k not in known_s_keys}
            status = str(s_data.get("status") or "ok")
            if status not in ("ok", "degraded", "error"):
                status = "ok"
            failures = s_data.get("consecutive_failures", 0)
            if not isinstance(failures, int) or failures < 0:
                failures = 0
            item_count = s_data.get("item_count", 0)
            if not isinstance(item_count, int) or item_count < 0:
                item_count = 0
            last_error = s_data.get("last_error")
            if isinstance(last_error, str) and last_error:
                last_error = redact_error(last_error)

            entry = SourceHealthEntry(
                status=status,
                last_success_at=s_data.get("last_success_at"),
                last_fetch_at=s_data.get("last_fetch_at"),
                consecutive_failures=failures,
                last_error=last_error,
                item_count=item_count,
                last_error_at=s_data.get("last_error_at"),
                extra_fields=extra if extra else None,
            )
            sources[source_id] = entry

        return _LoadedState(interface_version, updated_at, top_level_extra, sources, None)

    def _load(self) -> None:
        """Load state from disk without creating directories or mutating files."""
        state = self._read_state(self._file_path)
        if state.corrupt_content is not None:
            self._corrupt_content = state.corrupt_content
            return
        self._interface_version = state.interface_version
        self._updated_at = state.updated_at
        self._top_level_extra = state.top_level_extra
        self._sources = state.sources

    @staticmethod
    def _entry_in(sources: dict[str, SourceHealthEntry], source_id: str) -> SourceHealthEntry:
        entry = sources.get(source_id)
        if entry is None:
            entry = SourceHealthEntry(
                status="ok",
                last_success_at=None,
                last_fetch_at=None,
                consecutive_failures=0,
                last_error=None,
                item_count=0,
                last_error_at=None,
            )
            sources[source_id] = entry
        return entry

    def _apply_op(self, sources: dict[str, SourceHealthEntry], op: tuple[Any, ...]) -> None:
        """Apply one recorded outcome to sources state, live or replayed on save.

        Integer generation mirrors are monotonic: a stale lower mirror value
        never regresses a newer one.
        """
        kind, source_id = op[0], op[1]
        entry = self._entry_in(sources, source_id)
        if kind == "success":
            _, _, item_count, ts = op
            entry.status = "degraded" if entry.status == "error" else "ok"
            entry.consecutive_failures = 0
            entry.item_count = max(0, int(item_count))
            entry.last_success_at = ts
            entry.last_fetch_at = ts
            entry.last_error = None
            entry.last_error_at = None
        elif kind == "failure":
            _, _, error_text, ts = op
            entry.consecutive_failures += 1
            failures = entry.consecutive_failures
            if failures >= ERROR_THRESHOLD:
                entry.status = "error"
            elif failures >= DEGRADED_THRESHOLD:
                entry.status = "degraded"
            entry.last_error = error_text
            entry.last_error_at = ts
            entry.last_fetch_at = ts
        elif kind == "generation":
            _, _, generation = op
            extra = dict(entry.extra_fields) if entry.extra_fields else {}
            existing = extra.get("generation")
            stale = isinstance(existing, int) and isinstance(generation, int) and existing >= generation
            if not stale:
                extra["generation"] = generation
            entry.extra_fields = extra

    def should_fetch(self, source_id: str) -> bool:
        """Determine whether the source should be fetched in the current run.

        - 'ok': True
        - 'degraded': True
        - 'error': Blocked until 24h since last probe/failure, then one fetch is allowed.
        Skipped attempts are read-only and never count as failures or mutate disk.
        """
        if source_id not in self._sources:
            return True

        entry = self._sources[source_id]
        if entry.status != "error":
            return True

        # In error state: probe is allowed if at least 24h has elapsed since last error or fetch attempt
        reference_time_str = entry.last_error_at or entry.last_fetch_at
        if not reference_time_str:
            return True

        ref_dt = _parse_iso_datetime(reference_time_str)
        if ref_dt is None:
            return True

        now = self._now()
        if now - ref_dt >= BACKOFF_WINDOW:
            return True

        return False

    def record_success(self, source_id: str, item_count: int = 0) -> None:
        """Record a successful fetch for source_id.

        State transitions on success:
        - If previously in 'error' (probe succeeded): transitions to 'degraded' (two-step recovery).
          Consecutive failures are reset to 0.
        - If previously in 'degraded' or 'ok': transitions to 'ok'.
          Consecutive failures are reset to 0.
        Updates item_count, last_success_at, and last_fetch_at using genuine UTC time.
        """
        now_str = _format_iso_datetime(self._now())
        op = ("success", source_id, max(0, int(item_count)), now_str)
        self._pending_ops.append(op)
        self._apply_op(self._sources, op)

    def record_failure(self, source_id: str, error: Any) -> None:
        """Record a failed fetch attempt for source_id.

        State transitions on failure:
        - Increments consecutive_failures.
        - failure count < 3: status stays 'ok' (or remains 'degraded' if already degraded).
        - failure count >= 3 and < 10: status becomes 'degraded'.
        - failure count >= 10: status becomes 'error'.
        Updates last_error with redacted safe error string, last_error_at, and last_fetch_at.
        Does not mutate item_count or last_success_at.
        """
        now_str = _format_iso_datetime(self._now())
        op = ("failure", source_id, redact_error(error), now_str)
        self._pending_ops.append(op)
        self._apply_op(self._sources, op)

    def set_generation(self, source_id: str, generation: Any) -> None:
        """Mirror a lifecycle generation for source_id into the health entry.

        Parent collector calls this after a successful EventLifecycle.record_source
        and before save. Preserves status, counters, timestamps, and unknown fields.
        Integer mirrors are monotonic: a stale lower value never regresses a newer one.
        """
        op = ("generation", source_id, generation)
        self._pending_ops.append(op)
        self._apply_op(self._sources, op)

    @staticmethod
    def _render_payload(
        interface_version: str,
        top_level_extra: Mapping[str, Any],
        updated_at: str,
        sources: Mapping[str, SourceHealthEntry],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        payload.update(top_level_extra)
        payload.update(
            {
                "interface_version": interface_version or SCHEMA_VERSION,
                "updated_at": updated_at,
                "sources": {source_id: entry.to_dict() for source_id, entry in sources.items()},
            }
        )
        return payload

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable dictionary snapshot of current health state.

        Does not mutate disk. Preserves unknown top-level and source fields.
        """
        return self._render_payload(
            self._interface_version,
            self._top_level_extra,
            self._updated_at or _format_iso_datetime(self._now()),
            self._sources,
        )

    def _assert_writable_scope(self) -> None:
        for path in (self._file_path, self._file_path.with_suffix(".lock")):
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise SourceHealthCorruptError(f"refusing linked source health path: {path}")

    @contextmanager
    def _save_lock(self) -> Iterator[None]:
        """Serialize read-modify-write across overlapping stores and processes."""
        self._assert_writable_scope()
        self._topic_dir.mkdir(parents=True, exist_ok=True)
        self._assert_writable_scope()
        fd = os.open(self._file_path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def save(self) -> None:
        """Atomically persist health state to source-health.json in topic_dir.

        Raises SourceHealthCorruptError without writing anything when the on-disk
        file is corrupt or unreadable; repair or delete the file manually, then
        construct a fresh store.

        Runs as a locked read-modify-write: this store's recorded outcomes are
        replayed onto the freshest on-disk state under a file lock, so overlapping
        stores (for example a manual refresh overlapping the daily collector) never
        drop each other's outcomes. If topic_dir does not exist, it is created.
        Writes to a process-isolated temp file, flushes and fsyncs, then atomically
        replaces target.
        """
        if self._corrupt_content is not None:
            raise SourceHealthCorruptError(
                f"refusing to overwrite {self._file_path}: existing content is corrupt or "
                "unreadable; repair or delete the file manually, then reload the store"
            )
        now_str = _format_iso_datetime(self._now())

        with self._save_lock():
            state = self._read_state(self._file_path)
            if state.corrupt_content is not None:
                self._corrupt_content = state.corrupt_content
                raise SourceHealthCorruptError(
                    f"refusing to overwrite {self._file_path}: existing content is corrupt or "
                    "unreadable; repair or delete the file manually, then reload the store"
                )

            sources = state.sources
            for op in self._pending_ops:
                self._apply_op(sources, op)
            payload = self._render_payload(
                state.interface_version, state.top_level_extra, now_str, sources
            )
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

            fd, tmp_name = tempfile.mkstemp(prefix=".source-health.", suffix=".tmp", dir=self._topic_dir)
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._file_path)
            except Exception:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

        self._pending_ops.clear()
        self._sources = sources
        self._top_level_extra = state.top_level_extra
        self._interface_version = state.interface_version
        self._updated_at = now_str

    def get_source_display_name(self, source_id: str) -> str:
        """Resolve configured human display name, falling back to source_id."""
        return self._source_names.get(source_id) or source_id

    def report(self, language: str = "zh-CN") -> str:
        """Generate human-readable source health report.

        Requirements:
        - Purely read-only; does not mutate disk or create directories.
        - Names degraded and error sources using human-configured names (source_names).
        - Explains useful reasons with redacted errors.
        - Does NOT mislead with 'source disabled' when merely backed off.
        - Claims all-healthy only when every source has zero consecutive
          failures; sources with recent failures are listed separately.
        - Outside exact-five-actions digest footer contract.
        - No decorative status emojis required.
        """
        is_zh = language.lower().startswith("zh")
        if self._corrupt_content is not None:
            return (
                "信源健康状态不可用：文件损坏、不可读或链接越界；原文件保持不变。"
                if is_zh else "Source health unavailable: corrupt, unreadable, or linked state; original file preserved."
            )

        total_sources = len(self._sources)
        if total_sources == 0:
            return "信源状态良好，无异常。" if is_zh else "All sources healthy."

        ok_sources: list[str] = []
        recent_failures: list[tuple[str, SourceHealthEntry]] = []
        degraded_sources: list[tuple[str, SourceHealthEntry]] = []
        error_sources: list[tuple[str, SourceHealthEntry]] = []

        for source_id, entry in self._sources.items():
            if entry.status == "error":
                error_sources.append((source_id, entry))
            elif entry.status == "degraded":
                degraded_sources.append((source_id, entry))
            elif entry.consecutive_failures > 0:
                # Formal status is still 'ok', but the latest attempts failed:
                # never claim all-healthy while a fetch failure is on record.
                recent_failures.append((source_id, entry))
            else:
                ok_sources.append(source_id)

        if not degraded_sources and not error_sources and not recent_failures:
            return (
                f"全部 {total_sources} 个信源状态正常。"
                if is_zh
                else f"All {total_sources} sources are healthy."
            )

        lines: list[str] = []
        if is_zh:
            lines.append("## 信源健康监控")
            lines.append(f"- 正常信源：{len(ok_sources)} 个")
            if recent_failures:
                items_desc = []
                for sid, entry in recent_failures:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "本轮拉取失败"
                    items_desc.append(f"{name}（连续失败 {entry.consecutive_failures} 次，原因：{reason}）")
                lines.append(f"- 近期拉取失败信源（{len(recent_failures)} 个）：" + "；".join(items_desc))
            if degraded_sources:
                items_desc: list[str] = []
                for sid, entry in degraded_sources:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "请求失败"
                    items_desc.append(f"{name}（连续失败 {entry.consecutive_failures} 次，原因：{reason}）")
                lines.append(f"- 降级信源（{len(degraded_sources)} 个）：" + "；".join(items_desc))
            if error_sources:
                items_desc = []
                for sid, entry in error_sources:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "持续失败"
                    items_desc.append(
                        f"{name}（连续失败 {entry.consecutive_failures} 次，原因：{reason}，已暂缓拉取退避中）"
                    )
                lines.append(f"- 故障退避信源（{len(error_sources)} 个）：" + "；".join(items_desc))
        else:
            lines.append("## Source Health Monitoring")
            lines.append(f"- Healthy sources: {len(ok_sources)}")
            if recent_failures:
                items_desc = []
                for sid, entry in recent_failures:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "Fetch failed"
                    items_desc.append(
                        f"{name} ({entry.consecutive_failures} consecutive failures, reason: {reason})"
                    )
                lines.append(
                    f"- Recently failed sources ({len(recent_failures)}): " + "; ".join(items_desc)
                )
            if degraded_sources:
                items_desc = []
                for sid, entry in degraded_sources:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "Fetch failed"
                    items_desc.append(
                        f"{name} ({entry.consecutive_failures} consecutive failures, reason: {reason})"
                    )
                lines.append(f"- Degraded sources ({len(degraded_sources)}): " + "; ".join(items_desc))
            if error_sources:
                items_desc = []
                for sid, entry in error_sources:
                    name = self.get_source_display_name(sid)
                    reason = entry.last_error or "Persistent failure"
                    items_desc.append(
                        f"{name} ({entry.consecutive_failures} consecutive failures, reason: {reason}, backed off)"
                    )
                lines.append(f"- Backed-off sources ({len(error_sources)}): " + "; ".join(items_desc))

        return "\n".join(lines)
