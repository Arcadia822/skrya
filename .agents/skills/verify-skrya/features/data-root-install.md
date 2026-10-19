# Data root and install

Skrya keeps topics and runs in a data root resolved as `--data-root` > `SKRYA_DATA_ROOT` > `<workspace>/.skrya/config.json` > `~/.skrya/config.json` > `~/.skrya`. Installing the skill pack symlinks the skills into the host's global skill dir and writes the data-root config; uninstall has three modes that remove skills, data, or both.

## Sub-features

- `dr-show` prints the resolved data root and its source.
- `dr-set-home` persists a data root in `$HOME/.skrya/config.json` and creates `topics/` and `runs/` under it.
- `install-codex` symlinks `skrya` and `skrya-<skill>` into `$HOME/.codex/skills/` and writes the data-root config.
- `install-refuse-overwrite` refuses to replace an existing non-matching install target.
- `uninstall-skills` (`skills-keep-data`) removes installed skills, keeps data and config.
- `uninstall-complete` removes skills, the resolved data root, data-root configs, and marked `SKRYA-ROUTING-NOTE` blocks.
- `pack-upgrade` builds host assets in scratch, reports version, and runs explicit legacy Thread naming migration.

## How to get to it (user POV)

- User asks the agent to install Skrya (README Quick Start); the agent follows `INSTALL.md` and runs `install-skill-pack` / `./setup --host auto`.
- First-use flow asks where to store data; the agent runs `data-root --set <path> --scope home|workspace`.
- User asks to uninstall; the agent runs `uninstall-skill-pack --mode <mode>`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean. Installation/uninstall can modify the supplied root's packaging and routing notes: do not use the real checkout as root.
- Archive the current tracked source into the run's work directory, then use `R` for every command below:

  ```bash
  R="$($V path work)/checkout"
  mkdir -p "$R"
  git archive HEAD | tar -x -C "$R"
  ```

- The helper still selects checkout code through PYTHONPATH, while `--root "$R"` limits generated assets and instruction edits to scratch. HOME and SKRYA_DATA_ROOT remain isolated by the helper.

- **Show.** `$V skrya dr-show -- data-root --root "$R"` reports the scratch data root with source `SKRYA_DATA_ROOT`.
- **Persist home config.** `$V skrya dr-set -- data-root --root "$R" --set "$($V path work)/installed-data" --scope home`. Inspect the scratch HOME config and created directories; the helper's environment intentionally still wins over this saved config.
- **Build and upgrade.** `$V skrya build -- build-skill-pack --root "$R" --host all` and `$V skrya version -- version --root "$R"` must succeed. To prove migration, put a fixture `topics/migration-fixture/event-thread-seeds.json` under the scratch data root, run `$V skrya upgrade -- upgrade --root "$R" --migrate-thread-naming`, and inspect the new `thread-seeds.json`; legacy input remains for audit. Version/upstream checks may use the network.
- **Install for codex.** `$V skrya install -- install-skill-pack --root "$R" --host codex --data-root-mode custom --data-root-path "$($V path work)/installed-data" --data-root-config-scope home`. Snapshot. Expect root and five bundled skill links under the scratch HOME's `.codex/skills/`, with targets in scratch, plus a home data-root config.
- **Re-install side-effect invariant.** Save the six host links and list siblings of `R`, repeat the identical install, then compare both. Root output may become `in-place`; that alone is not failure or success. The host links should remain unchanged and no extra skill aliases should appear beside the source checkout. On an unexpected side effect, doctor and clean this session; use a fresh one for uninstall.
- **Uninstall skills only (fresh installation session).** `$V skrya uninstall-skills -- uninstall-skill-pack --root "$R" --host codex --mode skills-keep-data`. Snapshot: installed links are gone, but custom data and home config remain.
- **Complete uninstall last.** `$V skrya uninstall-complete -- uninstall-skill-pack --root "$R" --host codex --mode complete`. The helper's SKRYA_DATA_ROOT makes the resolved deletion target its seeded scratch data root. Confirm it and the home config are removed. This is not proof that a different custom data directory was removed.

## Gotchas

- `SKRYA_DATA_ROOT` set by the helper outranks every config file, so `data-root` (show) never reflects a `--set` you just made. To prove config precedence, compare `cat "$($V path home)/.skrya/config.json"` instead.
- Workspace-scope config and complete uninstall must use the archived `R`, even if doctor currently reports no real workspace config.
- Data-deleting uninstall ends that drive's useful lifetime; snapshot evidence, then cleanup and verify evidence retention.
- Known product gap: repeat install currently resolves the existing root link before calculating bundled target paths (`agent_assets.py:_install_host`), creating five extra `skrya-*` aliases beside `R` while original host links stay unchanged. Record this defect; do not change product code or redefine those extra aliases as intended idempotence.
- Snapshot `tree.txt` covers data and home, not the archived work tree. The helper separately writes `work-links.txt` for top-level work symlinks, so the extra install aliases remain visible after cleanup. With the real checkout as root those aliases could land beside the repository; this is why scratch `R` is mandatory.
- `--host auto` falls back to `codex` in the empty scratch HOME; pass `--host` explicitly.
