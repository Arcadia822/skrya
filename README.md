# Skrya

Skrya is a topic-driven briefing workspace that is now packaged as an installable skill pack.

The repository itself is the skill pack:

- `skill-pack.json` and `SKILL.md.tmpl` define the umbrella `skrya` skill.
- Each root skill directory such as `topic-curation/` or `digest/` defines one bundled skill.
- Generated `SKILL.md` files and `agents/openai.yaml` metadata are checked in beside their templates so an agent can use the pack immediately after installation.
- `skrya/` is a generated installer-facing umbrella skill directory for GitHub installers that only scan subdirectories for installable skills.
- Host-specific prompt-pack artifacts are generated under `.skrya/hosts/` at build time and are not source of truth.

## Core Workflow

Skrya's bundled skills are:

- `topic-curation`
- `request-curation`
- `source-curation`
- `digest`
- `deep-analysis`

Use `topic-curation` as the broad entry point whenever the user wants ongoing tracking or a briefing for some company, industry, market, product category, or theme without first naming an existing configured `topic-id`.

## Repository Structure

- `skill-pack.json`: umbrella skill metadata
- `SKILL.md.tmpl`: umbrella skill template
- `<skill>/skill.json`: metadata for a bundled skill
- `<skill>/SKILL.md.tmpl`: source template for a bundled skill
- `<skill>/SKILL.md`: generated runtime skill doc
- `<skill>/agents/openai.yaml`: generated OpenAI metadata
- `skrya/`: generated installer-facing umbrella skill directory
- `prompt-templates/`: source templates for `skrya-lite`, `skrya-full`, and `skrya-plan`
- `.skrya/hosts/`: generated host-specific prompt packs
- `topics/<topic-id>/`: durable topic configuration
- `runs/<topic-id>/`: generated digest and deep-analysis output
- `src/skrya_orchestrator/`: CLI, runtime intelligence, build, and install logic

## Topic Files

Each topic typically includes:

- `topic.json`
- `brief.json`
- `sources.json`
- `digest.md`
- `deep-analysis.md`

## Install

### Option 1: Clone directly into the agent skill directory

For Codex:

```powershell
git clone https://github.com/your-org/skrya.git $HOME/.codex/skills/skrya
cd $HOME/.codex/skills/skrya
python -m pip install -e .
python -m skrya_orchestrator.main build-skill-pack --root . --host codex
```

Because the repository already contains the generated root and bundled `SKILL.md` files, cloning into the final skill location is enough for direct discovery.

### Option 2: Clone anywhere, then install globally

```powershell
git clone https://github.com/your-org/skrya.git D:\work\skrya
cd D:\work\skrya
python -m pip install -e .
python -m skrya_orchestrator.main install-skill-pack --root . --host codex
```

There is also a convenience wrapper:

```powershell
./setup.ps1 --host codex
```

On Unix-like shells:

```bash
./setup --host codex
```

`install-skill-pack` builds the runtime pack, generates host prompt artifacts, and then installs Skrya into the selected global skill directory. It prefers a symlink and falls back to a copy if symlinks are unavailable.

For Codex-style installs, Skrya now follows a gstack-like split:

- the repo is installed as the main global `skrya` skill
- bundled skills such as `digest`, `deep-analysis`, and `topic-curation` are also installed into the same global skills root as namespaced entries like `skrya-digest`
- those bundled entries prefer symlinks back into the installed `skrya` repo and fall back to copies if symlinks are unavailable

## Build

Regenerate the checked-in runtime skill docs and the runtime host prompt artifacts:

```powershell
python -m skrya_orchestrator.main build-skill-pack --root . --host all
```

`build-agent-assets` remains as a backward-compatible alias, but `build-skill-pack` is the primary command now.

## Digest And Analysis Commands

Generate a digest:

```powershell
python -m skrya_orchestrator.main digest --topic k-entertainment --root .
```

Continue with a deep analysis:

```powershell
python -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root .
```

## Source Of Truth

If you need to change agent-facing behavior:

1. Edit `skill-pack.json` and `SKILL.md.tmpl` for the umbrella skill.
2. Edit `<skill>/skill.json` and `<skill>/SKILL.md.tmpl` for bundled skills.
3. Edit `prompt-templates/` for host prompt packs.
4. Run `python -m skrya_orchestrator.main build-skill-pack --root . --host all`.
5. Update tests and docs with the behavior change.

Do not hand-edit `.skrya/hosts/` or treat it as source of truth.

## Design Docs

Helpful docs for understanding the current model:

- [current-system-design.md](D:/Documents/skrya/design/current-system-design.md)
- [core-skills-spec.md](D:/Documents/skrya/design/core-skills-spec.md)
- [2026-04-18-skrya-installable-skill-pack-design.md](D:/Documents/skrya/docs/superpowers/specs/2026-04-18-skrya-installable-skill-pack-design.md)
- [2026-04-18-skrya-installable-skill-pack.md](D:/Documents/skrya/docs/superpowers/plans/2026-04-18-skrya-installable-skill-pack.md)

## Tests

```powershell
python -m unittest discover -s tests -v
```
