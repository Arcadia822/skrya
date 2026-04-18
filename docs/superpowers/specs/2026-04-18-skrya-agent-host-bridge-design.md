# Skrya Agent Host Bridge Design

**Date:** 2026-04-18

## Goal

Add a lightweight, gstack-style skill and host generation layer so Skrya can expose the same topic workflow cleanly to multiple agents without hand-maintaining separate copies of the prompts.

## Problem

Today the repo already has useful workspace rules and several skills, but the packaging is still manual:

1. `skills/` is both the source of truth and the delivery format.
2. Only part of the intended skill set is actually materialized.
3. There is no host-aware generation path for Codex, Claude Code, or OpenClaw.
4. There is no thin injected prompt pack equivalent to `gstack-lite`, `gstack-full`, and `gstack-plan`.

That makes the project understandable to a careful reader, but not yet predictable for an arbitrary agent or orchestrator.

## Desired End State

After this change:

1. Skill source-of-truth lives in one place and generated outputs live in well-known host roots.
2. Skrya has a complete first-pass skill surface: `request-curation`, `source-curation`, `topic-curation`, `digest`, and `deep-analysis`.
3. A single builder command can regenerate workspace skills plus host-specific skill roots.
4. Thin prompt packs exist for small edits, full execution, and planning-only sessions.
5. Repository docs explain which files humans should edit and which files are generated artifacts.

## Architecture

### 1. Source-of-Truth Skill Templates

Add `skills-src/` as the single authoring surface.

Each skill source directory contains:

- `skill.json` for stable metadata
- `SKILL.md.tmpl` for the markdown body

The builder owns frontmatter generation and host-specific metadata emission.

### 2. Declarative Host Configs In Python

Implement host configs in code for:

- `workspace`
- `codex`
- `claude`
- `openclaw`

Each host defines:

- output skill root
- instruction file name used in templates
- whether `agents/openai.yaml` should be emitted
- prompt-pack output filename style

The first version should keep rewrites intentionally small. The main value is consistent output paths and consistent packaging, not a large adapter framework yet.

### 3. Builder Command

Extend the CLI with:

```powershell
python -m skrya_orchestrator.main build-agent-assets --root . --host all
```

This command should:

1. Load skill templates from `skills-src/`
2. Render host outputs
3. Write skill artifacts into the configured host roots
4. Render `skrya-lite`, `skrya-full`, and `skrya-plan` prompt packs

### 4. Generated Outputs

The builder should materialize:

- `skills/<skill>/SKILL.md`
- `skills/<skill>/agents/openai.yaml`
- `.agents/skills/<skill>/...`
- `.claude/skills/<skill>/...`
- `.openclaw/skills/<skill>/...`
- `agent-hosts/<host>/skrya-lite-*`
- `agent-hosts/<host>/skrya-full-*`
- `agent-hosts/<host>/skrya-plan-*`

### 5. Skill Topology

Keep `topic-curation` as the user-facing entrypoint for broad topic configuration requests.

Add two narrower skills:

- `request-curation`: turns feedback about what matters into durable `brief.json` language
- `source-curation`: turns confirmed source intent into `sources.json` changes under the RSS-only rule

This keeps the repo-level routing simple while making internal responsibilities clearer.

## Non-Goals

1. Build a full gstack-style install system with global user-home deployment.
2. Port every host-specific tool quirk into custom adapters on day one.
3. Re-architect the digest/deep-analysis retrieval logic itself.

## Risks

1. Generated assets can drift from docs if the builder is added without tests.
2. Introducing source templates without updating README will confuse future editors.
3. Hidden host directories can feel noisy unless their role is documented clearly.

## Success Criteria

This work is successful when:

1. Missing skills are present and generated from `skills-src/`.
2. `build-agent-assets` can regenerate all checked-in agent assets from one source.
3. README and core design docs tell contributors to edit the source templates, not the generated copies.
4. Tests cover the builder and host outputs well enough to catch template drift.

