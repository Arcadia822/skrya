# Skrya Current System Design

## Purpose

Skrya is a topic-driven briefing workspace with an installable skill-pack surface.

It serves two jobs at once:

1. A runtime workspace for digest and deep-analysis generation.
2. A repository-native skill pack that an agent can install and use directly.

## Current Model

The repository is the skill pack.

### Runtime Intelligence

Runtime digest and analysis behavior lives in:

- `src/skrya_orchestrator/intelligence.py`
- `src/skrya_orchestrator/main.py`

That layer owns:

- topic file loading
- event ranking
- digest rendering
- deep-analysis resolution
- source lookup for on-demand disclosure

### Skill-Pack Surface

The repository root exposes:

- `skill-pack.json`
- `SKILL.md.tmpl`
- generated `SKILL.md`
- generated `agents/openai.yaml`
- generated `skrya/SKILL.md`
- generated `skrya/agents/openai.yaml`

Each bundled skill lives in its own root directory:

- `topic-curation/`
- `request-curation/`
- `source-curation/`
- `digest/`
- `deep-analysis/`

Each skill directory contains:

- `skill.json`
- `SKILL.md.tmpl`
- generated `SKILL.md`
- generated `agents/openai.yaml`

This lets the repo behave like gstack-style installable skill packs: after cloning into an agent skill directory, the agent can discover the umbrella skill and the bundled subskills without first generating workspace-only copies.

The extra `skrya/` directory exists for GitHub installers that only install subdirectories containing `SKILL.md`. It mirrors the umbrella skill so a user can say "install arcadia822/skrya" and still get the global `skrya` entry even if the installer ignores the repo root.

### Prompt Packs

Host prompt-pack templates live in `prompt-templates/`.

Generated host artifacts are written under:

- `.skrya/hosts/workspace/`
- `.skrya/hosts/codex/`
- `.skrya/hosts/claude/`
- `.skrya/hosts/openclaw/`

These are runtime artifacts only. They are not source of truth and are ignored by git.

## Installation Model

Skrya now supports two install shapes:

1. Clone directly into a global skill directory such as `~/.codex/skills/skrya`
2. Clone anywhere, then run `install-skill-pack` or `setup` to install globally

The installer builds the prompt-pack artifacts and then installs the repository into the host skill directory. It prefers a symlink and falls back to a copy when symlinks are unavailable.

For hosts like Codex, installation now happens in two layers:

1. install the repo as the main global `skrya` skill
2. install each bundled skill as its own namespaced global skill entry such as `skrya-digest`, preferably as a symlink into the installed `skrya` repo

## Data Root And Topic Files

Skrya separates the skill repository from user data. `--root` continues to point at the skill-pack or workspace root; topic configuration and generated history live under the resolved Skrya data root.

Resolution order:

1. explicit CLI `--data-root`
2. `SKRYA_DATA_ROOT`
3. workspace config at `.skrya/config.json`
4. home config at `~/.skrya/config.json`
5. default `~/.skrya`

For OpenClaw and container sandboxes, installation can write a workspace config that points to `.skrya/data`, so state remains inside the mounted workspace instead of the skill repository or an ephemeral home directory.

Durable topic configuration lives under `<skrya-data-root>/topics/<topic-id>/`:

- `topic.json`
- `brief.json`
- `sources.json`
- `digest.md`
- `deep-analysis.md`

Generated outputs live under `<skrya-data-root>/runs/<topic-id>/`.

The checked-in `topics/` directory is treated as examples and fixtures. It is no longer the default location for user topic memory.

## Main Architectural Shift

The previous model treated the repository as a source workspace that generated other host-facing skill trees such as `skills/`, `.agents/skills/`, `.claude/skills/`, and `.openclaw/skills/`.

The current model treats the repository itself as the installable runtime skill tree.

That means:

- no checked-in duplicated host skill directories
- no separate `skills-src/` authoring tree
- source templates and generated runtime docs live together
- host-specific packaging is pushed down into `.skrya/hosts/` and the installer
