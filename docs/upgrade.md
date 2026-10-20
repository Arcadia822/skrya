# Skrya Upgrade Flow

Use this when an agent has cloned a newer Skrya version or when a user asks to update Skrya.

## 1. Inspect The Current Install

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main version --root . --check-latest
PYTHONPATH=src python3 -m skrya_orchestrator.main data-root --root .
```

If a visible upstream revision is newer, ask the user whether to update before pulling or replacing files.

## 2. Update The Code

Use the host's normal non-destructive update path, for example:

```bash
git pull --ff-only
```

If the repository was freshly cloned into a skill directory, keep existing runtime user data under the configured Skrya data root. Do not copy runtime data into the skill-pack source tree unless the host explicitly uses workspace `.skrya/data`.

## 3. Run Required Migrations
Before running any migration, back up the current data root (for example copy `~/.skrya` or the workspace `.skrya/data` aside). Migrations copy files or write their own backups instead of deleting, but the data root is the only long-term store of topic config, digests, threads, and ingest history.

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-thread-naming
```

When moving older workspace-local `topics/` and `runs/` into the configured data root, run:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-data --migrate-thread-naming
```

This migration currently handles:

- workspace `topics/` and `runs/` copied into the configured data root when requested
- `event-thread-seeds.json` copied to `thread-seeds.json`
- `runs/<topic-id>/event-threads/latest-event-threads.json` copied to `runs/<topic-id>/threads/latest-threads.json`
- legacy payload keys and interface strings rewritten to `thread`

The migration copies missing new files and leaves legacy files in place for rollback and audit.

### Migrate Ingest State To v2

If topics were ingested by an older Skrya that still wrote `skrya.ingest.v1`, run the explicit conversion:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-ingest-v2
```

- The migration converts only each topic's current `runs/<topic-id>/ingest/latest-ingest.json` and first writes a `latest-ingest.v1-backup.json` backup beside it. Keep the data-root backup until you have reviewed the converted current state. Review any per-topic failures before resuming live collection. An optional `--topic <topic-id>` scopes the run to one topic.
- Archived normalized/raw ingest batches, digests, `.events.json` snapshots, Thread artifacts, delivery receipts, and bindings are never rewritten, and no frozen history is re-keyed.
- The migration is idempotent: rerunning reports `Already ingest v2` for topics already converted and changes nothing.
- There is no v1 runtime fallback. After the code update, ingest and digest reject `skrya.ingest.v1` payloads and print this migration command instead of silently converting on load. Old v1 frozen digest snapshots stay readable for N-xx/T-xx reference resolution.
- The migration is data-only. It does not modify skill-pack artifacts, does not delete anything, and does not run packaging repair. Legacy duplicate cleanup happens only in the explicit `build-skill-pack` and `install-skill-pack` steps below.


## 4. Rebuild Skill Artifacts

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

If this is a global skill install, reinstall for the active host:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

Upgrading the source checkout never silently changes a global skill install: rebuilding artifacts and reinstalling for the active host are explicit steps, and a plain `upgrade` run leaves both alone.

The root `SKILL.md` is canonical for the Skrya umbrella skill; no duplicate nested `skrya/SKILL.md` is generated. The `upgrade` command does not modify skill artifacts; legacy duplicate repair runs only during `build-skill-pack` and `install-skill-pack` (rebuild or reinstall). Rebuilding artifacts cleans up legacy generated duplicate metadata (`skrya/SKILL.md` and `skrya/agents/openai.yaml`) while preserving unrelated nested files such as `skrya/evals/` or custom notes. Repair preflights every candidate before deleting anything, so a later conflict never leaves a partially removed legacy entry behind; after a successful repair with nothing custom left, the empty `skrya/` nested entry is removed. A symlinked `skrya/agents` directory, a symlinked candidate file, or duplicate metadata that does not match the canonical generated counterpart is treated as an unknown conflict: the builder refuses the repair, reports it, and deletes nothing inside or outside the pack. Domain source presets under `source-curation/presets/` are copied alongside templates during build and install so recommendations travel with the skill pack.

The source checkout now keeps evaluation cases, the bank, reports and host fixtures under root `evals/`. The evaluation config and scripts load the canonical root skill directly; do not restore a nested `SKILL.md` to run evaluations. Legacy install repair still preserves user-owned nested evaluation directories rather than moving or deleting them.

Repeating a symlink-based install keeps the six skill entries in the active host's skill directory; it must not create `skrya-*` aliases beside the source checkout. Existing matching links are reused, and unrelated install targets are never overwritten. This does not remove stray aliases left by older installers: inspect their targets before deleting them manually.

## 5. Post-Upgrade Operations
### Collection and current-event state

Confirm enabled feed sources before running a live digest. RSSHub instances and routes must be user-confirmed; presets are advisory, not a reachability guarantee. A failed RSSHub source produces a provider-neutral retrieval request for the agent to cover that same source. Python does not call an external search provider or silently rewrite source configuration. Search tool APIs are unchanged.

Ingest v2 records `source_id`, `event_id`, `content_hash`, and per-source `source_generations`. Identity uses the exact article URL, or normalized title when absent; content hashes cover normalized title, summary, and content. Successful non-preview collection advances a source generation, including successfully parsed cached responses. Failed or skipped collection does not advance it. Current events use the latest source generation while older event records and full raw Thread history remain stored.

Only identical event-ID/content-hash pairs in the last three real digest snapshots are hidden. Changed content can appear again. Preview does not write caches, health, lifecycle state, or digest snapshots. Archived snapshots retain their original keys and hashes.

### Persistent caches

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main digest --topic <topic-id> --root . --force-refresh
PYTHONPATH=src python3 -m skrya_orchestrator.main cache --root . --clear-http-cache
PYTHONPATH=src python3 -m skrya_orchestrator.main cache --root . --clear-translation-cache --translation-language zh-CN
PYTHONPATH=src python3 -m skrya_orchestrator.main cache --root . --cleanup-expired
```

- `--force-refresh` bypasses HTTP cache freshness for one digest run; it does not clear anything.
- `cache` acts only on recognized cache entries under the data root, needs no topic, and reports what it removed. It does not clear ingest or Thread history. Running `cache` with no action flags prints usage and clears nothing.
- The translation cache is a non-expiring content-hash cache (keyed by language and provider); `--clear-translation-cache` without `--translation-language` clears every recognized entry.

### Source health diagnostics

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main source-health --topic <topic-id> --root .
PYTHONPATH=src python3 -m skrya_orchestrator.main source-health --topic <topic-id> --root . --refresh
```

- Without `--refresh`, the report reads the stored per-source health state and changes nothing.
- `--refresh` performs one live collection for that explicit topic and updates its health state; `--force-refresh` additionally bypasses HTTP cache freshness. Backed-off sources are reported as temporary backoff, never as disabled.

### Ingest pruning (dry-run first)

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main ingest-prune --topic <topic-id> --root . --keep 10
PYTHONPATH=src python3 -m skrya_orchestrator.main ingest-prune --topic <topic-id> --root . --keep 10 --apply
```

- Without `--apply`, the command only reports which raw/normalized ingest batches would be deleted. `--apply` recomputes and prints the current selection before deleting it. Avoid concurrent ingest writes between review and application; if new batches arrive, review a fresh dry run.
- The newest `--keep` batches (default 10) and the batch matching `latest-ingest.json` are always protected. The command never traverses outside the topic's ingest subtree, never follows symlinked entries, and never touches digests, `.events.json` snapshots, Thread artifacts, receipts, or bindings.

## 6. Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m skrya_orchestrator.main digest --topic <topic-id> --root . --sample
```

Check that the digest contains uniform N-xx items, every active Thread and exactly five actions. No decorative line boxes or user-facing runtime metadata remain. Render the same artifact with `render-card`, then resolve a news and Thread reference against its immutable `.events.json` sidecar. Preview must not create a new formal artifact or update latest pointers.

For native Feishu delivery, follow [channel adapters](channel-adapters.md). Preserve existing credentials, explicit destinations and scheduler ownership on each host. Existing bindings with no layout continue as `full-card`; new native Feishu bindings use `summary+thread`. Do not change production delivery or send a test message as part of this upgrade without authorization. A read-only `delivery-check` is not delivery proof.
