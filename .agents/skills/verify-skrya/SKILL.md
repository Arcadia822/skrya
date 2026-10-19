---
name: verify-skrya
description: Verify Skrya (topic-driven briefing skill pack) by driving its real `skrya_orchestrator` CLI from this checkout — digest, deep-analysis, threads, retrieval/ingest, template validation, data-root and skill-pack install — against an isolated scratch data root and HOME, capturing command/stdout/stderr/exit-code and written-artifact evidence. Use after changing anything under src/skrya_orchestrator/, digest templates, topic fixtures, or install/data-root behavior, or whenever you need proof that a Skrya CLI path works end to end.
---

# verify-skrya

Skrya is a skill pack: agents read `SKILL.md` files and call one deterministic surface, the Python CLI `python3 -m skrya_orchestrator.main <command>` (package `src/skrya_orchestrator/`). That CLI is what this skill drives. There is no server, port, or UI.

Not drivable here: the conversational flows in `topic-curation/`, `source-curation/`, `request-curation/` (pure prompt instructions; verify them by reading the generated SKILL.md, not by running code), and `npm run eval:skills*` (a mock OpenClaw runtime, not the real app).

The helper `scripts/verify-skrya` (executable, bash) wraps every call so it:

- runs from the repo root with `PYTHONPATH=<repo>/src` → code under test is this checkout, never the pipx `skrya` on PATH (`~/.local/bin/skrya` is a separate, possibly stale install);
- sets `SKRYA_DATA_ROOT=/tmp/verify-skrya-<run>/data` → never touches `~/.skrya`;
- sets `HOME=/tmp/verify-skrya-<run>/home` → install/uninstall/`data-root --set --scope home` write there, not into `~/.codex`, `~/.claude`, `~/.skrya/config.json`;
- passes `PYTHONUSERBASE` through so PyYAML from the user site still imports under the fake HOME;
- records `cmd.txt`, `stdout.txt`, `stderr.txt`, `exit_code` per call.

Runs are fully isolated (unique scratch dir per run), so concurrent runs are safe.

## Launch

No build step. Prereqs: `python3` ≥ 3.10 with PyYAML importable (`python3 -c "import yaml"`).

```bash
V=.agents/skills/verify-skrya/scripts/verify-skrya   # from repo root
eval "$($V launch)"          # exports VERIFY_SKRYA_RUN=<timestamp>-<pid>
```

`launch` creates `/tmp/verify-skrya-$VERIFY_SKRYA_RUN/{data,home,work}`, an owner marker, and seeds `data/topics/` with a copy of `tests/fixtures/topics/` (`agi-news`, `k-entertainment`, `new-energy-vehicles`). Ready = stderr line `verify-skrya: ready run=... scratch=... evidence=...`. It also writes `run.txt` (git HEAD, dirty file count, seeded topics) into the evidence dir.

Each shell needs `VERIFY_SKRYA_RUN` exported; if lost, recover it with `ls tmp/verify-skrya/evidence/`.

## Doctor

Run first, and again whenever anything looks off. Read-only.

```bash
$V doctor
```

Requires all `[OK]`: scratch dir owned by this run, evidence dir exists, `skrya_orchestrator` imports from `<repo>/src` (not site-packages/pipx), `version` prints `Skrya version:` + local revision, `data-root` reports `Source: SKRYA_DATA_ROOT` pointing inside the scratch dir. Any `[FAIL]` → exit 1; fix before driving. A `module/yaml import` failure means PyYAML is missing for this `python3` (override interpreter with `VERIFY_SKRYA_PYTHON=/path/to/python`).

## Drive

```bash
$V skrya <label> -- <cli args...>     # prints stdout, stderr tail, exit code; returns CLI exit code
$V snapshot <label>                   # copies data/runs/ + ls -lR of data/ and home/ into evidence
$V path data|home|work|scratch|evidence
```

Always pass `--root .` (the helper's cwd is the repo root). Do not pass `--data-root` unless the feature is about data-root precedence; `SKRYA_DATA_ROOT` already isolates. Files you need to feed the CLI (ingest JSON, candidate templates) go in `$($V path work)`.

Core commands (exact flags from `main.py`):

| User action | Command |
|---|---|
| Daily digest (writes artifacts) | `digest --root . --topic <id-or-name> [--sample]` |
| Test run / preview (no artifacts) | `digest --root . --topic <id> --preview` (alias `--test-run`) |
| Follow-up `dig: N` | `deep-analysis --root . --topic <id> --event-number N` |
| Thread timeline | `thread --root . --topic <id> --thread <id-or-name>` |
| Rebuild threads | `refresh-threads --root . --topic <id>` |
| Retrieval request | `retrieval-request --root . --topic <id> [--since ISO] [--until ISO]` |
| Record normalized retrieval | `ingest --root . --topic <id> --file <skrya.ingest.v1 json> [--raw-file f]` |
| Template save gate | `validate-digest-template --root . --file <md>` |
| Data root | `data-root --root . [--set P --scope home\|workspace] [--migrate]` |
| Install / uninstall | `install-skill-pack --root . --host codex\|claude\|openclaw ...` / `uninstall-skill-pack ...` |

Topic arguments accept the topic id or its `topic.json` `name` (e.g. `新能源汽车`). Errors surface as Python tracebacks on stderr with exit 1; the last stderr line is the user-meaningful message.

Feature recipes with exact commands and expected observations: `features/README.md`.

## Evidence

Location: `<repo>/tmp/verify-skrya/evidence/<run>/` (`tmp/` is gitignored). One numbered step dir per helper call: `NN-<label>/{cmd.txt,stdout.txt,stderr.txt,exit_code}`; snapshots: `NN-snapshot-<label>/{tree.txt,runs/}`.

Proof standards:

- Drive the real CLI entry point (`python -m skrya_orchestrator.main`), not `IntelligenceService` methods or test helpers.
- Capture the action and the resulting state: the call's stdout/exit code **and** a `snapshot` of what it wrote (`runs/<topic>/digest-*.md`, `latest-digest.md` symlink target, `latest-digest-events.json`, `deep-analysis-N.md`, `threads/latest-threads.json`, `ingest/...`).
- For mutations, prove with a second read: e.g. after `digest`, `deep-analysis` resolving the same item number; after `ingest`, a `digest --preview` whose items and `扫描时间范围` come from the ingested file.
- Check side effects by observation, not by name: `--preview` is proven side-effect-free by a snapshot showing no `runs/<topic>/` was created/changed. Do not trust "preview" alone.
- Known network touches even in "offline" paths: every `digest` runs `git ls-remote origin main` (3 s timeout, for the version-check line); non-`--sample` digest of an RSS topic (`k-entertainment`) fetches live feeds; zh-CN topics call Google Translate for non-Chinese text. Fixtures are Chinese and `--sample` avoids RSS, so seeded runs stay offline apart from `ls-remote`. Report network use if your run depends on it.
- The `## 系统提示` `Agent：`/`LLM：` lines come from env vars (`CLAUDECODE`, `CODEX_*`, `SKRYA_LLM_MODEL`, `MODEL`…), so they differ between hosts; don't assert on them.

## Cleanup

```bash
$V cleanup            # or: $V cleanup <run-id>
```

Removes only `/tmp/verify-skrya-<run>/` and only if its owner marker matches the run id; refuses otherwise. It also deletes `<repo>/.skrya/config.json` when (and only when) that file points into this run's scratch dir, since `data-root --set ... --scope workspace` writes it in the real checkout. No processes are started, so nothing to kill. Evidence under `tmp/verify-skrya/evidence/<run>/` is kept; confirm with `ls tmp/verify-skrya/evidence/<run>/`. Run cleanup after failed iterations too; orphaned runs show up as `ls -d /tmp/verify-skrya-*`, and you clean each one with `$V cleanup <run-id>`. Delete old evidence by hand only when the user no longer needs it.

If a step ran `build-skill-pack` or `install-skill-pack`, it regenerated `.skrya/hosts/` in the repo (gitignored, deterministic output); check `git status --short` shows no tracked changes.

## Gotchas

- Never call bare `skrya` or `python3 -m skrya_orchestrator.main` outside the helper for verification: real `~/.skrya` and real `~/.codex/skills` would be used.
- `deep-analysis` and `thread` read artifacts from the last non-preview `digest`; on a fresh run they fail with `Digest artifact not found` / `Thread artifact not found`. Run a real `digest` first.
- `uninstall-skill-pack --mode data-keep-skills|complete` deletes the resolved data root — under the helper that is the scratch `data/`, so later steps lose the seeded topics. Do it last or re-launch.
- `uninstall-skill-pack --mode complete` also strips `SKRYA-ROUTING-NOTE` blocks from `<repo>/AGENTS.md`/`CLAUDE.md` (repo files, not HOME). The current `AGENTS.md` has none; check `git diff --stat` afterward.
- `install-skill-pack --host auto` picks hosts by marker dirs in HOME; the scratch HOME has none, so it falls back to `codex`. Pass `--host` explicitly.
