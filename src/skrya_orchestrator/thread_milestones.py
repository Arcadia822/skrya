"""Project explicitly curated, sourced milestones without discarding raw history."""
from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse


def recorded_date(value: Any) -> str:
    """Accept complete ISO/RFC dates, never truncated RFC text or collection dates."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt is not None and dt.year >= 1900:
            return dt.date().isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return ""


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def select_milestones(timeline: list[dict]) -> list[dict]:
    """Importance is an editorial judgment, not recency or a keyword heuristic.

    Producers record milestone_reason on selected archival entries. Missing dates,
    missing sources and unreviewed news remain available to full-history consumers.
    """
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("milestone_reason") or "").strip()
        if not reason:
            continue

        milestone_date_raw = str(entry.get("milestone_date") or "").strip()
        milestone_basis = str(entry.get("milestone_date_basis") or "").strip()

        if milestone_date_raw:
            if not milestone_basis:
                continue
            event_date = recorded_date(milestone_date_raw)
        else:
            event_date = recorded_date(entry.get("date"))

        headline = str(
            entry.get("milestone_title")
            or entry.get("headline")
            or entry.get("title")
            or ""
        ).strip()

        sources = [
            s.get("url", "") if isinstance(s, dict) else str(s)
            for s in entry.get("sources", [])
        ]
        valid_sources = [s.strip() for s in sources if _is_valid_url(s.strip())]

        key = (event_date, headline)
        if not event_date or not headline or not valid_sources or key in seen:
            continue
        seen.add(key)
        selected.append({**entry, "date": event_date, "headline": headline, "sources": valid_sources})
    return sorted(selected, key=lambda entry: entry["date"])
