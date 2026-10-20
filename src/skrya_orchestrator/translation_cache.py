from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any


def _has_symlink_ancestor(path: Path) -> bool:
    """Fail closed when path or any of its ancestors is a symlink.

    Mirrors HttpCache boundary enforcement: an explicitly selected data-root alias
    is resolved once at construction, so anything linked below it is never followed.
    """
    return path.is_symlink() or any(
        parent.is_symlink() for parent in path.absolute().parents
    )


class TranslationCache:
    """Persistent content-hash translation cache isolating target language and provider."""

    def __init__(
        self,
        data_root: Path | str,
        *,
        clock: Callable[[], datetime | str] | None = None,
    ) -> None:
        self._data_root = Path(data_root).resolve(strict=False)
        self._cache_dir = self._data_root / "cache" / "translations"
        self._clock = clock

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def _now_iso(self) -> str:
        if self._clock is not None:
            now = self._clock()
            if isinstance(now, datetime):
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                return now.isoformat()
            if isinstance(now, str):
                return now
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def content_hash(text: str) -> str:
        """Compute 16-hex content hash over normalized whitespace."""
        normalized = " ".join(text.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _safe_lang(language: str) -> str:
        if not language or not isinstance(language, str):
            raise ValueError("language must be a non-empty string")
        if (
            ".." in language
            or "/" in language
            or "\\" in language
            or "\0" in language
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", language)
            or language in (".", "..")
            or language.startswith(".")
        ):
            raise ValueError(f"Invalid language code: {language!r}")
        return language

    @staticmethod
    def _provider_key(provider: str) -> str:
        if not provider or not isinstance(provider, str):
            raise ValueError("provider must be a non-empty string")
        if (
            re.fullmatch(r"[A-Za-z0-9_.-]+", provider)
            and provider not in (".", "..")
            and not provider.startswith(".")
            and ".." not in provider
            and len(provider) <= 64
        ):
            return provider
        return hashlib.sha256(provider.encode("utf-8")).hexdigest()[:16]

    def _entry_path(self, language: str, provider: str, h: str) -> Path:
        lang_dir = self._safe_lang(language)
        prov_dir = self._provider_key(provider)
        if not re.fullmatch(r"[a-f0-9]+", h):
            raise ValueError(f"Invalid content hash: {h!r}")
        return self._cache_dir / lang_dir / prov_dir / f"{h}.json"

    def _entry_usable(self, entry_path: Path) -> bool:
        """Report whether the cache entry may be read or written.

        Fails closed on linked cache ancestry (including a linked cache root or
        parent) and on entries resolving outside the cache base: such entries are
        ignored entirely instead of being read, written, or deleted through links.
        """
        if _has_symlink_ancestor(entry_path):
            return False
        resolved_base = self._cache_dir.resolve(strict=False)
        try:
            entry_path.resolve(strict=False).relative_to(resolved_base)
        except ValueError:
            return False
        return True

    def _atomic_write(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_ancestor(file_path):
            return
        tmp_name = f".{file_path.name}.tmp.{os.getpid()}.{time.time_ns()}"
        tmp_path = file_path.with_name(tmp_name)
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except OSError:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def translate(
        self,
        text: str,
        translator: Callable[[str], str],
        *,
        language: str = "zh-CN",
        provider: str = "google-translate",
        write: bool = True,
    ) -> str:
        if not isinstance(text, str) or not text.strip():
            return text

        h = self.content_hash(text)
        entry_path = self._entry_path(language, provider, h)
        cache_usable = self._entry_usable(entry_path)

        if cache_usable and entry_path.is_file():
            payload = None
            try:
                raw = entry_path.read_text(encoding="utf-8")
                payload = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None

            if isinstance(payload, dict):
                source_text = payload.get("source_text")
                cached_translation = payload.get("translated_text")
                try:
                    valid = (
                        payload.get("content_hash") == h
                        and payload.get("lang") == language
                        and payload.get("model") == provider
                        and isinstance(source_text, str)
                        and self.content_hash(source_text) == h
                        and isinstance(cached_translation, str)
                        and bool(cached_translation.strip())
                        and cached_translation.strip() != text.strip()
                        and cached_translation.strip() != source_text.strip()
                    )
                except UnicodeEncodeError:
                    # Corrupted entry (e.g. lone surrogate in source_text):
                    # treat as a miss so the translator runs and the cache is
                    # repaired below.
                    valid = False
                if valid:
                    return cached_translation

        try:
            translated = translator(text)
        except Exception:
            return text

        if not isinstance(translated, str) or not translated.strip():
            return text

        if translated.strip() == text.strip():
            return text

        if write and cache_usable:
            payload = {
                "source_text": text,
                "translated_text": translated,
                "content_hash": h,
                "lang": language,
                "model": provider,
                "created_at": self._now_iso(),
            }
            self._atomic_write(entry_path, payload)

        return translated

    def clear(self, *, language: str | None = None) -> int:
        lang_key: str | None = None
        if language is not None:
            lang_key = self._safe_lang(language)
            resolved_base = self._cache_dir.resolve(strict=False)
            resolved_search = (self._cache_dir / lang_key).resolve(strict=False)
            try:
                resolved_search.relative_to(resolved_base)
            except ValueError:
                raise ValueError(f"Path traversal detected: {language}")

        if _has_symlink_ancestor(self._cache_dir):
            return 0

        if not self._cache_dir.exists():
            return 0

        if lang_key is not None:
            search_dir = self._cache_dir / lang_key
        else:
            search_dir = self._cache_dir

        if not search_dir.exists():
            return 0

        removed_count = 0
        resolved_base = self._cache_dir.resolve(strict=False)

        for path in list(search_dir.rglob("*.json")):
            if not path.is_file():
                continue
            if path.is_symlink() or path.name.startswith("."):
                continue

            try:
                rel = path.resolve(strict=False).relative_to(resolved_base)
            except ValueError:
                continue

            if len(rel.parts) != 3:
                continue

            entry_lang, entry_provider_dir, _ = rel.parts
            stem = path.stem
            if not re.fullmatch(r"[a-f0-9]{16}", stem):
                continue

            if lang_key is not None and entry_lang != lang_key:
                continue

            try:
                raw = path.read_text(encoding="utf-8")
                payload = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue

            if not isinstance(payload, dict):
                continue

            content_hash = payload.get("content_hash")
            payload_lang = payload.get("lang")
            payload_model = payload.get("model")
            source_text = payload.get("source_text")
            translated_text = payload.get("translated_text")

            if not isinstance(payload_model, str) or not payload_model.strip():
                continue
            try:
                provider_key = self._provider_key(payload_model)
            except (ValueError, UnicodeEncodeError):
                continue

            try:
                source_hash_ok = (
                    isinstance(source_text, str)
                    and self.content_hash(source_text) == stem
                )
            except UnicodeEncodeError:
                # Corrupted entry (e.g. lone surrogate in source_text): skip it
                # and keep processing the remaining entries.
                continue

            if (
                content_hash != stem
                or payload_lang != entry_lang
                or provider_key != entry_provider_dir
                or not source_hash_ok
                or not isinstance(translated_text, str)
                or not translated_text.strip()
            ):
                continue

            try:
                path.unlink()
                removed_count += 1
            except OSError:
                pass

        self._prune_empty_dirs(search_dir)
        return removed_count

    def _prune_empty_dirs(self, root: Path) -> None:
        if _has_symlink_ancestor(root) or not root.exists():
            return
        resolved_base = self._cache_dir.resolve(strict=False)
        for dirpath, _, _ in os.walk(str(root), topdown=False):
            current = Path(dirpath)
            try:
                current.resolve(strict=False).relative_to(resolved_base)
            except ValueError:
                continue
            if current == self._data_root or current == self._data_root / "cache":
                continue
            try:
                current.rmdir()
            except OSError:
                pass
