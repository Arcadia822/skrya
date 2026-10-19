# Skrya verification map

This directory is the maintained source for verifying the user-facing behavior of Skrya's CLI (`python3 -m skrya_orchestrator.main`). Agents reach these commands when a user asks for a digest, replies `dig: N`, asks about a thread, connects a retrieval source, edits a digest template, or installs Skrya. Read this index first, then use the matching feature file as the recipe.

## Baseline preconditions

- Work from the repo root with `V=.agents/skills/verify-skrya/scripts/verify-skrya`.
- `eval "$($V launch)"` created a fresh run; `VERIFY_SKRYA_RUN` is exported in this shell.
- `$V doctor` prints only `[OK]` lines (a `[WARN]` about `.skrya/config.json` forbids workspace-scope writes).
- The scratch data root holds the three seeded topics `agi-news` (runtime-retrieval sources, no ingest yet), `k-entertainment` (5 live RSS sources), and `new-energy-vehicles` (runtime-retrieval sources + one active thread seed `byd-flash-charge-station` / `比亚迪闪充站`). All have `language: zh-CN` and a `sample-events.json`.
- No `runs/` directory exists until a non-preview command writes one.

## Driving conventions

- Every CLI call goes through `$V skrya <label> -- <args>`. Never call `skrya` or the module directly.
- Always pass `--root .`. Do not pass `--data-root` except when testing data-root precedence.
- Put input files (ingest payloads, candidate templates) under `$($V path work)`.
- Treat commands as literal. Topic ids and Chinese topic/thread names are both valid references.
- Use `--sample` to stay offline on topics with RSS sources. Without it, `k-entertainment` fetches live feeds.
- Features that depend on a prior digest (`deep-analysis`, `thread`) must run a non-preview `digest` in the same run first.

## Proof and skip reporting

- CLI proof is the step dir `tmp/verify-skrya/evidence/<run>/NN-<label>/` with `cmd.txt`, `stdout.txt`, `stderr.txt`, `exit_code`.
- Mutation proof adds `$V snapshot <label>` after the call, plus a read-only second command that consumes what was written.
- Side-effect-free claims (`--preview`) need a snapshot showing nothing was written.
- Error-path proof is exit code `1` plus the last stderr line naming the cause.
- Record the feature file and sub-feature ID used in your report alongside the evidence path.
- Report an unreachable path with the attempted command and the unmet precondition. Do not report a path as verified through a different entry point.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify-skrya` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

## Features

- [Daily digest](./daily-digest.md) covers real digest runs, test-run preview, active-thread timeline section, empty state, artifacts, and the `latest-digest.md` pointer.
- [Deep analysis](./deep-analysis.md) covers `dig: N` follow-ups resolved against the latest digest, and the missing-digest / bad-number errors.
- [Event threads](./threads.md) covers thread timelines by id or alias and thread refresh.
- [Retrieval and ingest](./retrieval-ingest.md) covers provider-neutral retrieval requests, recording normalized `skrya.ingest.v1` results, and digests built from them.
- [Digest template validation](./digest-template-validation.md) covers the template save gate.
- [Data root and install](./data-root-install.md) covers data-root resolution, persisted config, skill-pack install, and uninstall modes.
