# Translation Cache

Persistent content-hash translation cache module for Skrya topic intelligence.

## Motivation

Topic digest generation frequently processes repetitive cross-run events.
Querying external translation APIs on every run incurs unnecessary network round-trips and risk of rate limits.
The translation cache persists successful translations keyed by normalized content hash, language, and translation provider.

## Storage Layout

All cache entries are stored beneath the resolved data root.
The module does not create any directories in its constructor.

```text
<data_root>/cache/translations/<lang>/<provider-or-provider-hash>/<content-hash>.json
```

- `<lang>`: Target language code, `zh-CN` or `en` for supported topic output.
- `<provider-or-provider-hash>`: Provider identifier such as `google-translate` or a 16-character SHA-256 hash when provider contains unsafe path characters.
- `<content-hash>.json`: 16-character SHA-256 hash of whitespace-normalized source text.

## Entry Schema

Cache entry files are formatted as UTF-8 JSON.

```json
{
  "source_text": "OpenAI launches ChatGPT agent browser",
  "translated_text": "OpenAI 推出 ChatGPT 代理浏览器",
  "content_hash": "a1b2c3d4e5f60718",
  "lang": "zh-CN",
  "model": "google-translate",
  "created_at": "2026-05-17T10:00:00+08:00"
}
```

- `source_text`: Raw original source string provided by caller.
- `translated_text`: Translated text string returned by translator.
- `content_hash`: 16-character hex hash computed over whitespace-normalized source text.
- `lang`: Target language tag.
- `model`: Translation provider identifier.
- `created_at`: ISO 8601 timestamp generated via injectable clock.

## Keying and Hashing

Source text whitespace is normalized before hashing.
Leading, trailing, and multi-line whitespace variations map to the same content hash.

```python
normalized = " ".join(text.split())
content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
```

## Security and Filename Safety

Target language and provider arguments are strictly guarded against path traversal.
Language values containing path separators, null bytes, or traversal sequences raise a `ValueError`.
Provider identifiers containing path separators or characters outside safe alphanumeric boundaries are securely hashed into a single 16-character hex directory name.
All resolved paths are verified against the cache root directory boundary before access.

## Caching and Fallback Semantics

The cache enforces strict caching rules to prevent cache poisoning:

1. **Non-empty changed translations**:
   A translation is cached only if it is non-empty and differs from the source text.
2. **Untranslated original fallback**:
   If an external translator returns the source text unchanged, the result is returned directly and is not cached.
3. **Empty or whitespace text**:
   Empty or whitespace strings return directly without calling the translator or writing cache entries.
4. **Exceptions**:
   If the translator raises an exception, the original text is returned as a fallback and no cache entry is written.
5. **Corrupted entries**:
   Unparseable or corrupted cache files are treated as cache misses and repaired atomically upon successful translation.
6. **Atomic writes**:
   Cache entries are written via temporary files and fsync before atomic replacement.
7. **Read-only preview mode**:
   Calling `translate(..., write=False)` never creates directories or writes files.

Chinese passthrough filtering remains the responsibility of `IntelligenceService`.
`TranslationCache` does not duplicate Chinese detection logic.

## Python API

```python
from skrya_orchestrator.translation_cache import TranslationCache

cache = TranslationCache(data_root, clock=None)

# Translate text with automatic caching
translated = cache.translate(
    text,
    translator_callable,
    language="zh-CN",
    provider="google-translate",
    write=True,
)

# Targeted clear for a specific language
removed_zh = cache.clear(language="zh-CN")

# Clear all owned translation cache files
removed_all = cache.clear()
```

## CLI integration

The `cache` subcommand clears translation cache entries without needing any topic or runs data:

```bash
skrya cache --root <workspace> --data-root <data-root> --clear-translation-cache
skrya cache --root <workspace> --data-root <data-root> --clear-translation-cache --translation-language zh-CN
```

- `--translation-language` requires `--clear-translation-cache`. An invalid combination returns exit code 2 without changing cache files.
- Without `--translation-language` the command clears every recognized translation cache entry across all languages and providers.
- With `--translation-language` (for example `zh-CN` or `en`) it scopes removal to that language directory.
- The command calls `TranslationCache(data_root).clear(language=...)` and reports the number of removed entries.
- Recognized entries are `<data_root>/cache/translations/<lang>/<provider>/<content-hash>.json` files; unknown files and directories are preserved.

## Caching contract for callers

- Only translations with an explicit provider identity persist under that provider's namespace; the default translation path uses `provider="google-translate"`.
- Injected translator functions without a declared provider identity bypass the persistent cache entirely instead of writing into the default provider namespace.
- Failures and unchanged translations are never cached, and `write=False` (used by digest previews) performs no filesystem writes.
- The translation cache does not expire entries; there is no time-based cleanup for this layer.
