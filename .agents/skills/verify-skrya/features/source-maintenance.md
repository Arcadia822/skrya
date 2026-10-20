# Source maintenance and lifecycle

Exercise RSSHub, source health, HTTP cache behavior, ingest lifecycle and preview isolation through the real CLI. A loopback fixture supplies synthetic Chinese feeds without external source credentials. These recipes are instructions, not evidence of an executed run.

## Sub-features

- `source-health` reports failures and source generations without silently changing source configuration.
- `rsshub-fallback` exposes neutral fallback retrieval for an unavailable source.
- `http-cache` serves warm data without another request and bypasses freshness on force refresh.
- `cache-maintenance` clears recognized cache entries, with no action defaulting to usage.
- `preview-equality` compares every data-root entry and file byte, not merely `runs/`.
- `lifecycle-repeat` hides unchanged pairs from the last three real snapshots, but includes changed content.
- `ingest-migration` explicitly converts current legacy ingest while retaining backups and frozen history.
- `ingest-prune` previews selected archived batches and applies only with explicit approval.

## How to get to it (user POV)

- User asks why a source failed, why an item repeated, or why a digest is empty.
- User explicitly asks to migrate ingest state or prune old ingest batches.
- Operator verifies source/cache behavior in an isolated run without touching user sources or installations.

## Driving it with verify-skrya

Preconditions:

- Run from the repository root. Use a fresh run for each destructive scenario.
- Use the existing helper, which isolates HOME/data-root and preserves PYTHONUSERBASE. Never replace it with bare CLI calls.
- Only fixture source configuration is approved here. Live external feeds, translation providers and remote delivery require separate approval.

- **Launch and cleanup.** Run this shell setup once. Cleanup stops the loopback server before removing scratch. It hashes evidence outside the evidence directory before and after cleanup, so the manifests do not hash themselves. Retain both manifests with the evidence. A failed equality check is a failure, not successful cleanup proof.

```bash
V=.agents/skills/verify-skrya/scripts/verify-skrya
F=.agents/skills/verify-skrya/scripts/maintenance-fixture.py
eval "$($V launch)"
W="$($V path work)"
D="$($V path data)"
E="$($V path evidence)"
FIXTURE_PID=
finish() {
  status=$?
  trap - EXIT
  if [ -n "$FIXTURE_PID" ]; then
    kill "$FIXTURE_PID" 2>/dev/null || true
    wait "$FIXTURE_PID" 2>/dev/null || true
  fi
  for artifact in requests.jsonl server.stdout server.stderr fixture-ready.json sources-original.json; do
    if [ -f "$W/$artifact" ]; then cp "$W/$artifact" "$E/$artifact" || status=1; fi
  done
  python3 "$F" manifest "$E" > "$E.before-cleanup.json"
  $V cleanup || status=1
  python3 "$F" manifest "$E" > "$E.after-cleanup.json"
  cmp "$E.before-cleanup.json" "$E.after-cleanup.json" || status=1
  exit "$status"
}
trap finish EXIT
$V doctor || exit $?
python3 "$F" serve "$($V path scratch)" > "$W/server.stdout" 2> "$W/server.stderr" &
FIXTURE_PID=$!
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  [ -f "$W/fixture-ready.json" ] && break
  sleep 1
done
[ -f "$W/fixture-ready.json" ] || exit 1
cp "$W/fixture-ready.json" "$E/fixture-ready.json"
```

- **Command failures.** The setup does not enable `set -e`. For every subsequent helper command inspect its exit status before proceeding. Unexpected nonzero means run doctor and stop the scenario. For expected failures, capture `$?`, run doctor immediately, and assert that captured status. The helper retains stdout/stderr and exit code, including failures. Before leaving the shell copy `requests.jsonl`, `server.stdout`, and `server.stderr` from work to evidence, including on a failed scenario if those files exist.

- **Health collection.** Run `$V skrya health-refresh -- source-health --root . --topic agi-news --refresh`, then `$V skrya health-read -- source-health --root . --topic agi-news` and `$V snapshot health`. Expect successful local feed collection and a recorded failure for `fixture-broken` under `topics/agi-news/source-health.json`. Only successful collection advances that source's generation; cache success can count as a collection, not a network request. `--force-refresh` on source-health implies collection and bypasses HTTP freshness. If the CLI instead reports that collector integration is required, record the path as blocked, run doctor, and stop rather than claiming refresh coverage through another command.

- **Fallback request.** `$V skrya fallback -- retrieval-request --root . --topic agi-news`. Inspect failed-source coverage and neutral capability/query records. Compare `sources.json` with `$W/sources-original.json`, which the fixture saved before collection. No provider or fallback activation may be silently persisted.

- **Mixed live and ingest.** Follow [Retrieval and ingest](retrieval-ingest.md) to record `$W/ingest.json`. Preview must include both the feed and ingest titles before any real digest. Use the equality procedure below around that preview.

- **Full-data-root equality.** Make these manifests outside the data root. Run once on a fresh root and once after real collection/ingest has populated health, event-state and caches. Capture directory entries, symlink targets and file hashes. Do not use modification times as byte equality. Manifest generation is read-only and never follows symlink directories.

```bash
python3 "$F" manifest "$D" > "$E/data-before-preview.json"
$V skrya preview -- digest --root . --topic agi-news --preview
preview_status=$?
if [ "$preview_status" -ne 0 ]; then $V doctor; exit "$preview_status"; fi
python3 "$F" manifest "$D" > "$E/data-after-preview.json"
cmp "$E/data-before-preview.json" "$E/data-after-preview.json" || exit 1
$V snapshot after-preview
```

- **HTTP warm cache and bypass.** Count `/feed` entries in `$W/requests.jsonl` before and after two successful `$V skrya warm-1 -- source-health --root . --topic agi-news --refresh` calls (use label `warm-2` for the second). The warm feed must not add requests within its TTL. Failed `/broken` requests are separate from the successful feed's cache proof. Then `$V skrya force -- source-health --root . --topic agi-news --force-refresh` must add a `/feed` request. Save the request log and snapshots. Do not treat a newly advanced source generation as proof of a network fetch.

- **Cache maintenance.** `$V skrya cache-usage -- cache --root .` must exit 2 without changing the data manifest; run doctor after that expected error. `$V skrya cache-http -- cache --root . --clear-http-cache` removes recognized HTTP entries. The next explicit collection must request `/feed` again. `$V skrya cache-expired -- cache --root . --cleanup-expired` is usable without a topic; fresh entries must remain. `$V skrya cache-zh -- cache --root . --clear-translation-cache --translation-language zh-CN` and `$V skrya cache-all-translations -- cache --root . --clear-translation-cache` exercise language-scoped and whole translation clearing. With this Chinese-only fixture the translation cache is normally empty. Report these as empty-cache CLI coverage, not translation-hit/TTL proof. Never seed guessed cache formats or borrow a user's cache to claim stronger coverage. Preserve unknown cache files and inspect reported removal counts and before/after snapshots.

- **Repeated real events.** On a fresh fixture run record ingest, then `$V skrya first-real -- digest --root . --topic agi-news` and snapshot. `$V skrya repeat-preview -- digest --root . --topic agi-news --preview` must not repeat unchanged N-items, though active Threads can still show their latest state. Repeat preview with full-root manifests; it must not advance dedup memory. Change `$W/feed-title.txt` to `验证用条目：本地信源修订推理评测基准`, leaving the article URL unchanged. `$V skrya changed -- digest --root . --topic agi-news --preview --force-refresh` must show the changed event. Compare stored original event IDs/hashes in the real digest sidecar against the unchanged `event-state.json` after preview. To prove the three-snapshot boundary, write three more real digests, then preview the original unchanged ingest again. It is eligible after its pair falls outside the last three real sidecars. Keep all sidecars and frozen reference keys intact.

- **Explicit migration regression fixture only.** In a fresh run record a valid ingest first, then save a full-root manifest and a copy of current latest under work. Change only the scratch `runs/agi-news/ingest/latest-ingest.json` interface to legacy format using this fixture conversion. Do not change any archived normalized/raw batches or snapshots.

```bash
python3 - "$D" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]) / 'runs/agi-news/ingest/latest-ingest.json'
payload = json.loads(p.read_text())
payload['interface_version'] = 'skrya.ingest.v1'  # Explicit migration regression input.
payload.pop('source_generations', None)
for item in payload['items']:
    for key in ('source_id', 'event_id', 'content_hash'):
        item.pop(key, None)
p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
PY
```

  Save those legacy bytes in work. A normal digest preview must reject them and request explicit migration; capture nonzero and run doctor. Run `$V skrya migrate -- upgrade --root . --topic agi-news --migrate-ingest-v2`, then snapshot and read current latest plus `latest-ingest.v1-backup.json`. Backup must equal the saved legacy bytes. Current latest has normalized identities and generations; archived batches/history remain byte-identical. Run migration again to prove idempotence, then preview the migrated ingest. Do not submit legacy payloads to the active ingest writer as a normal recipe.

- **Dry-run-first pruning.** Use the collision recipe to create at least four batches, retaining a snapshot before maintenance. Run `$V skrya prune-plan -- ingest-prune --root . --topic agi-news --keep 1`. Inspect selected normalized/raw pairs, latest-protected batch, `apply=false`, and empty `deleted`. A full-root manifest must remain equal across the dry run. Stop here unless the operator explicitly approves deletion of those scratch batches. Only then run `$V skrya prune-apply -- ingest-prune --root . --topic agi-news --keep 1 --apply`. Snapshot again and compare the actual deletion set to the reviewed plan. The latest batch, backups, digest sidecars, full Thread history, receipts and bindings must remain untouched. If the plan changed, obtain fresh approval rather than applying a different selection.

## Gotchas

- Launching the fixture overwrites only scratch `agi-news/sources.json`. Never point it at user data. It refuses roots without a matching verification owner marker.
- The fixture server is loopback-only, short-lived and separate from Skrya. Stop it before cleanup. Every Skrya action still uses the isolated CLI helper.
- `source-health --refresh` and migration must use the implemented CLI handlers, not direct Python service calls. Missing integration is a blocker to report, not permission to invent evidence.
- Captured health/cache generation changes are not request counts. Inspect the fixture's HTTP log.
- No recipe approves global installation, real data deletion, credentials, remote delivery or generated host-file edits.
