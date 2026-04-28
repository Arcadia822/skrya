# Install Skrya

This file is for agents and technical operators. The README is intentionally user-facing; it tells users what to ask their agent, not which commands to run.

## Install

Clone and install the skill pack:

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

Host-specific installs are also supported:

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host openai
python3 -m skrya_orchestrator.main install-skill-pack --root . --host claude
python3 -m skrya_orchestrator.main install-skill-pack --root . --host openclaw
```

Convenience scripts:

```bash
./scripts/install.sh --host auto
pwsh ./scripts/install.ps1 -Host auto
```

## Data Root

Check or set the Skrya data root:

```bash
python3 -m skrya_orchestrator.main data-root --root .
python3 -m skrya_orchestrator.main data-root --root . --set ~/.skrya
python3 -m skrya_orchestrator.main data-root --root . --set .skrya/data --migrate
```

Use `~/.skrya` for normal desktop hosts unless the user asks for workspace-scoped data. Use `.skrya/data` for OpenClaw-style or mounted-workspace hosts when state must stay inside the workspace.

## Uninstall

Skrya supports three uninstall modes:

- `skills-keep-data`: remove installed skills, keep topic config, history, and data-root config.
- `data-keep-skills`: remove Skrya data and data-root config, keep installed skills.
- `complete`: remove installed skills, data, data-root config, and marked Skrya routing notes in global instruction files.

Commands:

```bash
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --mode skills-keep-data
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --mode data-keep-skills
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --mode complete
```

Complete uninstall must only remove marked Skrya blocks such as `SKRYA-ROUTING-NOTE`. Do not clear unrelated `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, or `tools.md` content.

## Upgrade

When Skrya detects or suspects a newer version, tell the user there is an available update and ask before changing the installation.

Recommended flow:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main version --root . --check-latest
git pull --ff-only
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-thread-naming
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
PYTHONPATH=src python3 -m unittest discover -s tests
```

Read `docs/upgrade.md` before declaring the upgrade complete. If the upgrade guide lists required migrations or storage moves, run them and report what changed.
