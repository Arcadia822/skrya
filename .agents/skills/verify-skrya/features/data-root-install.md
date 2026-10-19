# Data root and install

Skrya keeps topics and runs in a data root resolved as `--data-root` > `SKRYA_DATA_ROOT` > `<workspace>/.skrya/config.json` > `~/.skrya/config.json` > `~/.skrya`. Installing the skill pack symlinks the skills into the host's global skill dir and writes the data-root config; uninstall has three modes that remove skills, data, or both.

## Sub-features

- `dr-show` prints the resolved data root and its source.
- `dr-set-home` persists a data root in `$HOME/.skrya/config.json` and creates `topics/` and `runs/` under it.
- `install-codex` symlinks `skrya` and `skrya-<skill>` into `$HOME/.codex/skills/` and writes the data-root config.
- `install-refuse-overwrite` refuses to replace an existing non-matching install target.
- `uninstall-skills` (`skills-keep-data`) removes installed skills, keeps data and config.
- `uninstall-complete` removes skills, the resolved data root, data-root configs, and marked `SKRYA-ROUTING-NOTE` blocks.

## How to get to it (user POV)

- User asks the agent to install Skrya (README Quick Start); the agent follows `INSTALL.md` and runs `install-skill-pack` / `./setup --host auto`.
- First-use flow asks where to store data; the agent runs `data-root --set <path> --scope home|workspace`.
- User asks to uninstall; the agent runs `uninstall-skill-pack --mode <mode>`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean, with no `[WARN]` about `.skrya/config.json`.
- The helper sets `HOME` to `$($V path home)` (empty) and `SKRYA_DATA_ROOT` to `$($V path data)`.

- **Show.** Run `$V skrya dr-show -- data-root --root .`. Stdout `Skrya data root: <scratch>/data` and `Source: SKRYA_DATA_ROOT`.
- **Install for codex.** Run `$V skrya install -- install-skill-pack --root . --host codex --data-root-mode custom --data-root-path "$($V path work)/installed-data" --data-root-config-scope home` then `$V snapshot after-install`. Stdout lists `codex/skrya: symlink -> <scratch>/home/.codex/skills/skrya` and five `codex/skrya-*` lines, then `data-root: <scratch>/work/installed-data (config: <scratch>/home/.skrya/config.json)`. `tree.txt` shows those symlinks under `home/.codex/skills/`.
- **Re-install is idempotent.** Run the same install again. Exit `0`; lines read `in-place` instead of `symlink`.
- **Uninstall skills only.** Run `$V skrya uninstall-skills -- uninstall-skill-pack --root . --host codex --mode skills-keep-data` then `$V snapshot after-uninstall`. Stdout has six `skill: removed -> ...` lines; `home/.skrya/config.json` and `work/installed-data/` still exist.
- **Complete uninstall (run last).** Run `$V skrya uninstall-complete -- uninstall-skill-pack --root . --host codex --mode complete`. Stdout includes `data-root: removed -> <scratch>/data` and `data-config: removed -> <scratch>/home/.skrya/config.json`. Afterwards `git status --short` shows no tracked changes (`AGENTS.md` has no routing-note block).

## Gotchas

- `SKRYA_DATA_ROOT` set by the helper outranks every config file, so `data-root` (show) never reflects a `--set` you just made. To prove config precedence, compare `cat "$($V path home)/.skrya/config.json"` instead.
- `data-root --set ... --scope workspace` writes `<repo>/.skrya/config.json` in the real checkout. `$V cleanup` removes it only when it points into this run's scratch dir; never run it when doctor warns about an existing file.
- `uninstall --mode data-keep-skills|complete` deletes the scratch `data/` (the seeded topics); run it last.
- `install-skill-pack` rebuilds `.skrya/hosts/` in the repo (gitignored generated output).
- `--host auto` falls back to `codex` in the empty scratch HOME; pass `--host` explicitly.
