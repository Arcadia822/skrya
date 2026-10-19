---
name: verify-skrya
description: Verify Skrya's real CLI from this checkout in isolated HOME and data roots, retaining command/output/artifact evidence. Covers digests, legacy numeric analysis, Threads, retrieval/ingest, template validation, native cards and frozen references, delivery preconditions, and install/uninstall. Use after changes to CLI behavior, templates, fixtures, delivery or installation.
---

# verify-skrya

Skrya is a skill pack: agents read `SKILL.md` files and call one deterministic surface, the Python CLI `python3 -m skrya_orchestrator.main <command>` (package `src/skrya_orchestrator/`). That CLI is what this skill drives. There is no server, port, or UI.

Conversational configuration flows and article drafting are agent workflows, not standalone CLI commands. Native cards can be rendered locally; actual Feishu delivery and desktop/mobile appearance require an explicitly approved sandbox application and recipient.

The helper `scripts/verify-skrya` (executable, bash) wraps every call so it:

- runs from the repo root with `PYTHONPATH=<repo>/src` → code under test is this checkout, never the pipx `skrya` on PATH (`~/.local/bin/skrya` is a separate, possibly stale install);
- sets `SKRYA_DATA_ROOT=/tmp/verify-skrya-<run>/data` → never touches `~/.skrya`;
- sets `HOME=/tmp/verify-skrya-<run>/home` → install/uninstall/`data-root --set --scope home` write there, not into `~/.codex`, `~/.claude`, `~/.skrya/config.json`;
- passes `PYTHONUSERBASE` through so PyYAML from the user site still imports under the fake HOME;
- records `cmd.txt`, `stdout.txt`, `stderr.txt`, `exit_code` per call.

Use a fresh isolated run for each feature recipe; drive its short-lived CLI processes serially. Run doctor before the first drive in every run and after every nonzero exit, including expected error cases. If doctor fails, do not continue driving until the cause is understood and health restored.

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
$V snapshot <label>                   # copies data/runs/, data/home tree and top-level work symlinks
$V path data|home|work|scratch|evidence
```

Pass `--root .` for ordinary commands. For installation, workspace data-root config and uninstall, first create an archived checkout under the run's `work/` and use it as `--root` (see `features/data-root-install.md`); never let those commands edit the real checkout's packaging or instructions. Do not pass `--data-root` except to verify precedence. Put inputs under `$($V path work)`.

Core commands (exact flags from `main.py`):

| User action | Command |
|---|---|
| Daily digest (writes artifacts) | `digest --root . --topic <id-or-name> [--sample]` |
| Test run / preview (no artifacts) | `digest --root . --topic <id> --preview` (alias `--test-run`) |
| Legacy numeric analysis | `deep-analysis --root . --topic <id> --event-number N`; current agent follow-ups use frozen resolution below |
| Thread timeline | `thread --root . --topic <id> --thread <id-or-name>` |
| Rebuild threads | `refresh-threads --root . --topic <id>` |
| Retrieval request | `retrieval-request --root . --topic <id> [--since ISO] [--until ISO]` |
| Record normalized retrieval | `ingest --root . --topic <id> --file <skrya.ingest.v1 json> [--raw-file f]` |
| Template save gate | `validate-digest-template --root . --file <md>` |
| Data root | `data-root --root . [--set P --scope home\|workspace] [--migrate]` |
| Install / uninstall | `install-skill-pack --root "$R" --host codex\|claude\|openclaw ...` / `uninstall-skill-pack --root "$R" ...`; R is the archived scratch checkout |
| Native card bundle | `render-card --root . --file <digest.md> --format feishu-v2 -o <bundle.json>` |
| Frozen local reference | `resolve-reference --root . --topic <id> --artifact <digest.md> --reference N-xx\|T-xx` |
| Delivery preflight / send | `delivery-check` / `deliver --channel feishu --topic <id> --target <bound-target> --binding <id>`; `deliver` also requires `--file` |
| Received reference | `resolve-reference --root . --topic <id> --binding <id> [--message-id <id>] --reference N-xx\|T-xx` |

Topic arguments accept the id or display name. Legacy digest/analysis/thread errors may end in a Python traceback; render/delivery/reference commands instead print a concise failure and exit 1. Inspect both exit code and captured stdout/stderr, not one assumed error format.

Feature recipes with exact commands and expected observations: `features/README.md`.

## Evidence

Location: `<repo>/tmp/verify-skrya/evidence/<run>/` (`tmp/` is gitignored). One numbered step dir per helper call: `NN-<label>/{cmd.txt,stdout.txt,stderr.txt,exit_code}`; snapshots: `NN-snapshot-<label>/{tree.txt,runs/}`.

Proof standards:

- Drive the real CLI entry point (`python -m skrya_orchestrator.main`), not `IntelligenceService` methods or test helpers.
- Capture the action and the resulting state: the call's stdout/exit code **and** a `snapshot` of what it wrote (`runs/<topic>/digest-*.md`, `latest-digest.md` symlink target, `latest-digest-events.json`, `deep-analysis-N.md`, `threads/latest-threads.json`, `ingest/...`).
- For mutations, prove with a second read: e.g. after `digest`, `deep-analysis` resolving the same item number; after `ingest`, a `digest --preview` whose items and `扫描时间范围` come from the ingested file.
- Check side effects by observation, not by name: `--preview` is proven side-effect-free by a snapshot showing no `runs/<topic>/` was created/changed. Do not trust "preview" alone.
- Network boundaries: live RSS retrieval and translation of non-Chinese text can use the network. Digest no longer adds a version-check footer. `doctor` invokes `version`, whose upstream check may use the network. Say when fixtures were used.
- Plain Markdown ends in five actions without model/version/Agent/LLM execution metadata. Native card date badges and layout are checked separately from archive dates.
- Before delivery-precondition tests, remove inherited `SKRYA_FEISHU_APP_ID`, `SKRYA_FEISHU_APP_SECRET`, and `SKRYA_FEISHU_CONFIG` from the helper's environment. Never borrow real credentials or bindings just to make a path reachable. `delivery-check` can contact the API even though it sends no message.
- With explicit sandbox authorization, a temporary local lark-cli transport boundary may drive the real CLI entry point while the CLI owns authentication. Follow `features/feishu-delivery.md`, capture the exact runner, and report separately what orchestration passed and which default-auth/transport paths were not exercised. A standalone CLI card send is not sender proof.

## Cleanup

```bash
$V cleanup            # or: $V cleanup <run-id>
```

Removes only `/tmp/verify-skrya-<run>/` and only if its owner marker matches the run id; refuses otherwise. It also deletes `<repo>/.skrya/config.json` when (and only when) that file points into this run's scratch dir, since `data-root --set ... --scope workspace` writes it in the real checkout. No processes are started, so nothing to kill. Evidence under `tmp/verify-skrya/evidence/<run>/` is kept; confirm with `ls tmp/verify-skrya/evidence/<run>/`. Run cleanup after failed iterations too; orphaned runs show up as `ls -d /tmp/verify-skrya-*`, and you clean each one with `$V cleanup <run-id>`. Delete old evidence by hand only when the user no longer needs it.

Always run cleanup in a `finally`/shell trap, including after failed drives. Before cleanup, enumerate the evidence files and record their hashes; afterward confirm they still exist unchanged at the named evidence directory. Scratch removal is not evidence retention proof.

- Build/install operations regenerate host assets under the supplied root. Use the archived root so no generated assets or product instructions are changed in the real checkout.

## Gotchas

- Never call bare `skrya` or an unisolated Python entry point for verification: real data and host skill directories would be used. The approved temporary Feishu CLI-boundary runner is the sole exception to the helper invocation shape, not to isolated HOME/data-root, doctor, evidence or cleanup requirements.
- `deep-analysis` and `thread` read artifacts from the last non-preview `digest`; on a fresh run they fail with `Digest artifact not found` / `Thread artifact not found`. Run a real `digest` first.
- `uninstall-skill-pack --mode data-keep-skills|complete` deletes the resolved data root — under the helper that is the scratch `data/`, so later steps lose the seeded topics. Do it last or re-launch.
- Complete uninstall may strip routing-note blocks in the supplied root. Use only the archived scratch checkout for this path; do not rely on the real repository currently lacking a marker.
- `install-skill-pack --host auto` picks hosts by marker dirs in HOME; the scratch HOME has none, so it falls back to `codex`. Pass `--host` explicitly.
