from __future__ import annotations

from dataclasses import dataclass
import hashlib
import queue
import re
import threading
import time
from typing import Any, Callable
import urllib.parse
import xml.etree.ElementTree as ET
from skrya_orchestrator.source_health import redact_error

__all__ = [
    "RsshubError",
    "RsshubConfigError",
    "RsshubUnavailable",
    "RsshubConfig",
    "parse_rsshub_config",
    "validate_route",
    "validate_instance_url",
    "build_rsshub_url",
    "validate_feed_xml",
    "MAX_ACTIVE_REQUESTS",
]


class RsshubError(Exception):
    """Base exception for all RSSHub connector errors."""


class RsshubConfigError(RsshubError, ValueError):
    """Raised when RSSHub source configuration is invalid."""


class RsshubUnavailable(RsshubError):
    """Raised when all configured RSSHub instances fail or return invalid feeds."""

    def __init__(
        self,
        message: str,
        *,
        source_id: str | None = None,
        error_summary: str | None = None,
        route: str | None = None,
        failures: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source_id = source_id
        self.error_summary = error_summary or message
        self.route = route
        self.failures = list(failures or [])

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class RsshubConfig:
    route: str
    instance_urls: tuple[str, ...]
    timeout_ms: int = 3500
    hedge_delay_ms: int = 300
    source_id: str | None = None


MAX_ACTIVE_REQUESTS = 4
_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def validate_route(route: Any) -> str:
    """Validate that route is a relative path without scheme or host escape.

    Returns normalized route string starting with '/'.
    """
    if not isinstance(route, str):
        raise RsshubConfigError(f"Route must be a string, got {type(route).__name__}")

    trimmed = route.strip()
    if not trimmed:
        raise RsshubConfigError("Route cannot be empty or blank")

    if "\\" in trimmed:
        raise RsshubConfigError("Route must not contain backslashes")

    if _SCHEME_PATTERN.match(trimmed) or trimmed.startswith(("http:", "https:", "ftp:")):
        raise RsshubConfigError("Route must be a relative path, not an absolute URL")

    if trimmed.startswith("//"):
        raise RsshubConfigError("Route must not start with '//'")

    parsed = urllib.parse.urlsplit(trimmed)
    if parsed.scheme:
        raise RsshubConfigError("Route must not contain a URL scheme")
    if parsed.netloc:
        raise RsshubConfigError("Route must not contain a host")

    path_only = parsed.path
    segments = path_only.split("/")
    depth = 0
    for seg in segments:
        if seg == "..":
            depth -= 1
            if depth < 0:
                raise RsshubConfigError("Route attempts to escape host via '..'")
        elif seg and seg != ".":
            depth += 1

    if "/../" in trimmed or trimmed.startswith("../") or trimmed == ".." or trimmed.endswith("/.."):
        raise RsshubConfigError("Route attempts to escape host via '..'")

    return "/" + trimmed.lstrip("/")


def validate_instance_url(url: Any) -> str:
    """Validate that an instance URL is HTTP(S) without credentials, queries, or fragments.

    Requires a non-empty hostname and a valid numeric port. Rejection messages never
    echo the rejected URL so credential-bearing configuration cannot leak through
    config errors.

    Returns normalized instance URL with trailing slash stripped.
    """
    if not isinstance(url, str):
        raise RsshubConfigError(f"Instance URL must be a string, got {type(url).__name__}")

    trimmed = url.strip()
    if not trimmed:
        raise RsshubConfigError("Instance URL cannot be empty or blank")

    try:
        parsed = urllib.parse.urlsplit(trimmed)
    except ValueError as exc:
        raise RsshubConfigError(
            f"Instance URL could not be parsed ({type(exc).__name__})"
        ) from exc

    if parsed.scheme not in ("http", "https"):
        raise RsshubConfigError(
            f"Instance URL must have 'http' or 'https' scheme, got {parsed.scheme!r}"
        )

    if not parsed.netloc:
        raise RsshubConfigError("Instance URL must have a valid host")

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise RsshubConfigError(
            f"Instance URL has an invalid hostname or port ({type(exc).__name__})"
        ) from exc

    if not hostname or any(ch.isspace() for ch in hostname):
        raise RsshubConfigError("Instance URL must have a non-empty hostname")

    if port is not None and not (0 < port <= 65535):
        raise RsshubConfigError("Instance URL port must be between 1 and 65535")

    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise RsshubConfigError("Instance URL must not contain credentials")

    if parsed.query:
        raise RsshubConfigError("Instance URL must not contain query parameters")

    if parsed.fragment:
        raise RsshubConfigError("Instance URL must not contain URL fragments")

    return trimmed.rstrip("/")


def parse_rsshub_config(source: dict[str, Any]) -> RsshubConfig:
    """Parse and validate RSSHub configuration from source dictionary at the system boundary."""
    if not isinstance(source, dict):
        raise RsshubConfigError(f"Source configuration must be a dict, got {type(source).__name__}")

    raw_route = source.get("route")
    route = validate_route(raw_route)

    raw_instances = source.get("instance_urls")
    if raw_instances is None and "instance" in source:
        inst = source.get("instance")
        if isinstance(inst, str) and inst.strip():
            raw_instances = [inst]

    if raw_instances is None:
        raise RsshubConfigError("source must explicitly configure 'instance_urls'")

    if not isinstance(raw_instances, (list, tuple)):
        raise RsshubConfigError(
            f"'instance_urls' must be a list or tuple of strings, got {type(raw_instances).__name__}"
        )

    if len(raw_instances) == 0:
        raise RsshubConfigError("'instance_urls' cannot be empty")

    validated_instances = tuple(validate_instance_url(u) for u in raw_instances)

    raw_timeout = source.get("timeout_ms", 3500)
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
        raise RsshubConfigError(
            f"timeout_ms must be a positive number, got {type(raw_timeout).__name__}"
        )
    if raw_timeout <= 0:
        raise RsshubConfigError(f"timeout_ms must be positive, got {raw_timeout!r}")
    timeout_ms = int(raw_timeout)

    raw_hedge = source.get("hedge_delay_ms", 300)
    if isinstance(raw_hedge, bool) or not isinstance(raw_hedge, (int, float)):
        raise RsshubConfigError(
            f"hedge_delay_ms must be a non-negative number, got {type(raw_hedge).__name__}"
        )
    if raw_hedge < 0:
        raise RsshubConfigError("hedge_delay_ms must be non-negative")
    hedge_delay_ms = int(raw_hedge)

    source_id = source.get("id") or source.get("name") or source.get("source_id")
    if source_id is not None:
        source_id = str(source_id)

    return RsshubConfig(
        route=route,
        instance_urls=validated_instances,
        timeout_ms=timeout_ms,
        hedge_delay_ms=hedge_delay_ms,
        source_id=source_id,
    )


def build_rsshub_url(instance_url: str, route: str) -> str:
    """Build full URL for an instance and route, ensuring route does not escape the host."""
    clean_base = instance_url.rstrip("/")
    clean_route = route.lstrip("/")
    full_url = f"{clean_base}/{clean_route}"

    base_parsed = urllib.parse.urlsplit(clean_base)
    full_parsed = urllib.parse.urlsplit(full_url)
    if full_parsed.netloc != base_parsed.netloc or full_parsed.scheme != base_parsed.scheme:
        raise RsshubConfigError(
            f"Constructed URL {redact_error(full_url)} escaped instance host {base_parsed.netloc!r}"
        )
    return full_url


def validate_feed_xml(content: str) -> bool:
    """Check if content is a valid RSS, Atom, or RDF XML feed."""
    if not isinstance(content, str):
        return False

    stripped = content.strip()
    if not stripped:
        return False

    if stripped.lower().startswith("<!doctype html"):
        return False

    try:
        root = ET.fromstring(stripped.encode("utf-8"))
    except Exception:
        return False

    tag = root.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]

    return tag.lower() in ("rss", "feed", "rdf")


def _summarize_body(content: str) -> str:
    """Return a short, safe description of an invalid response body."""
    if not content or not content.strip():
        return "empty response"

    stripped = content.strip()
    if stripped.lower().startswith("<!doctype html") or "<html" in stripped.lower()[:200]:
        if re.search(r"<title[^>]*>.*?</title>", stripped, re.IGNORECASE | re.DOTALL):
            return "HTML error page with <title> (title content withheld)"
        return "HTML page instead of XML feed"

    try:
        root = ET.fromstring(stripped.encode("utf-8"))
        tag = root.tag.split("}", 1)[1] if "}" in root.tag else root.tag
        return f"XML document with non-feed root tag: <{tag}>"
    except Exception as exc:
        return f"malformed XML: {type(exc).__name__}"


def fetch_rsshub(source: dict[str, Any], fetch: Callable[[str, float], str]) -> str:
    """Fetch an RSSHub source using hedged requests across configured instances.

    Parameters:
        source: Source dictionary specifying route, instance_urls, timeout_ms, hedge_delay_ms.
        fetch: Callable accepting (url: str, timeout_seconds: float) returning raw body text.

    Returns:
        The raw XML text of the first valid RSS/Atom feed response.

    Raises:
        RsshubConfigError: If configuration is invalid.
        RsshubUnavailable: If all instances fail, return invalid feeds, or time out.
    """
    config = parse_rsshub_config(source)
    safe_route = f"route:{hashlib.sha256(config.route.encode('utf-8')).hexdigest()}"
    safe_source_id = redact_error(config.source_id) if config.source_id else config.source_id
    source_id = safe_source_id or f"rsshub:{safe_route}"
    timeout_sec = config.timeout_ms / 1000.0
    stagger_sec = config.hedge_delay_ms / 1000.0

    target_urls = [build_rsshub_url(inst, config.route) for inst in config.instance_urls]
    num_instances = len(target_urls)

    def diagnostic_origin(url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    # Queue item: (status: str, idx: int, url: str, body: str | None, error_desc: str | None)
    results_queue: queue.Queue[tuple[str, int, str, str | None, str | None]] = queue.Queue()
    stop_event = threading.Event()

    def _worker(idx: int, url: str) -> None:
        if stop_event.is_set():
            return
        try:
            body = fetch(url, timeout_sec)
            if stop_event.is_set():
                return
            if validate_feed_xml(body):
                results_queue.put(("success", idx, url, body, None))
            else:
                summary = _summarize_body(body)
                results_queue.put(("invalid_feed", idx, url, None, summary))
        except Exception as exc:
            if stop_event.is_set():
                return
            safe_error = str(exc).replace(url, diagnostic_origin(url))
            safe_error = safe_error.replace(config.instance_urls[idx], diagnostic_origin(url))
            results_queue.put(("error", idx, url, None, redact_error(safe_error.replace(config.route, safe_route))))

    threads: list[threading.Thread] = []
    failures: list[dict[str, Any]] = []
    completed_idxs: set[int] = set()

    def _launch(idx: int) -> None:
        url = target_urls[idx]
        try:
            t = threading.Thread(
                target=_worker,
                args=(idx, url),
                name=f"rsshub-hedge-{idx}",
                daemon=True,
            )
            threads.append(t)
            t.start()
        except Exception as exc:
            # Thread.start() failures must not escape the connector error path; they
            # are reported through the normal failure channel with a redacted reason.
            results_queue.put(
                ("error", idx, url, None, redact_error(f"request could not be started: {exc}"))
            )

    _launch(0)
    next_launch_idx = 1
    next_hedge_time = time.monotonic() + stagger_sec
    active_in_flight = 1

    total_deadline = time.monotonic() + ((num_instances - 1) * stagger_sec) + timeout_sec

    while active_in_flight > 0 or next_launch_idx < num_instances:
        now = time.monotonic()
        if now >= total_deadline:
            break

        can_launch = next_launch_idx < num_instances and active_in_flight < MAX_ACTIVE_REQUESTS
        if can_launch:
            wait_time = max(0.0, min(next_hedge_time - now, total_deadline - now))
        else:
            wait_time = max(0.0, total_deadline - now)

        try:
            item = results_queue.get(timeout=wait_time)
            status, idx, url, body, err = item
            active_in_flight -= 1
            completed_idxs.add(idx)

            if status == "success":
                stop_event.set()
                return body  # Return immediately, never waiting for losing requests

            failures.append({
                "instance_url": diagnostic_origin(url),
                "status": status,
                "error": err or "unknown failure",
            })

            # If all active requests have finished and failed, launch the next hedge early
            if active_in_flight == 0 and next_launch_idx < num_instances:
                _launch(next_launch_idx)
                next_launch_idx += 1
                next_hedge_time = time.monotonic() + stagger_sec
                active_in_flight += 1

        except queue.Empty:
            now = time.monotonic()
            if (
                next_launch_idx < num_instances
                and active_in_flight < MAX_ACTIVE_REQUESTS
                and now >= next_hedge_time
            ):
                _launch(next_launch_idx)
                next_launch_idx += 1
                next_hedge_time = now + stagger_sec
                active_in_flight += 1


    stop_event.set()

    for idx in range(min(next_launch_idx, num_instances)):
        if idx not in completed_idxs:
            failures.append({
                "instance_url": diagnostic_origin(target_urls[idx]),
                "status": "timeout",
                "error": f"timed out within deadline ({timeout_sec:.2f}s budget)",
            })

    for idx in range(next_launch_idx, num_instances):
        failures.append({
            "instance_url": diagnostic_origin(target_urls[idx]),
            "status": "not_attempted",
            "error": "not launched (active-request cap or deadline reached)",
        })

    summary_parts = [f"{f['instance_url']}: [{f['status']}] {f['error']}" for f in failures]
    safe_summary = (
        f"All {num_instances} RSSHub instances failed: "
        + "; ".join(summary_parts)
    )
    error_message = f"RSSHub source unavailable: {safe_summary}"

    raise RsshubUnavailable(
        error_message,
        source_id=source_id,
        error_summary=safe_summary,
        route=safe_route,
        failures=failures,
    )
