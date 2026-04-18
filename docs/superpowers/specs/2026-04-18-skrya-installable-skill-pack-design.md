# Skrya Installable Skill Pack Design

**Date:** 2026-04-18

## Goal

Make Skrya behave like an installable skill pack instead of a repository that only emits checked-in host-specific output trees.

## Problem

The previous model solved template reuse, but it still looked like an internal workspace:

1. source templates lived in `skills-src/`
2. generated host trees such as `.agents/skills/` and `.claude/skills/` were first-class checked-in directories
3. the repository root was not itself the runtime skill pack
4. installation required understanding the generation model first

That made Skrya understandable to contributors, but it did not create the same "install it and the agent can already use it" effect the user wants from gstack.

## Desired End State

After this change:

1. the repository root exposes a real umbrella `skrya` skill
2. bundled skills live as first-class root directories beside the umbrella skill
3. generated runtime docs are checked in beside their templates
4. host-specific prompt-pack artifacts move into a gitignored runtime area
5. installation becomes clone-directly or run-one-installer

## Architecture

### 1. Repository-Native Skill Pack

Add:

- `skill-pack.json`
- `SKILL.md.tmpl`
- generated `SKILL.md`
- generated `agents/openai.yaml`

This defines the umbrella skill.

Each bundled skill becomes a root directory with:

- `skill.json`
- `SKILL.md.tmpl`
- generated `SKILL.md`
- generated `agents/openai.yaml`

### 2. Host Runtime Artifacts

Keep host-specific prompt packs, but move them to:

- `.skrya/hosts/workspace/`
- `.skrya/hosts/codex/`
- `.skrya/hosts/claude/`
- `.skrya/hosts/openclaw/`

These are build outputs, not checked-in source trees.

### 3. Builder Changes

The builder must now:

1. generate the umbrella skill in place
2. generate bundled runtime skill docs in place
3. generate host prompt packs under `.skrya/hosts/`

### 4. Installer Changes

Add a global installer that:

1. builds the runtime pack
2. detects or accepts the target host
3. installs the repository into the host skill directory
4. prefers symlink install, with copy fallback

### 5. Backward Compatibility

Keep `build-agent-assets` as an alias for `build-skill-pack` so older scripts do not fail immediately.

## Non-Goals

1. Rewriting the digest or deep-analysis intelligence layer.
2. Mirroring every gstack install trick exactly.
3. Adding a large per-host adapter framework before it is needed.

## Success Criteria

This work is successful when:

1. Skrya has a root `SKILL.md` and root metadata.
2. Bundled skills are discoverable directly from the repository layout.
3. Checked-in `.agents`, `.claude`, `.openclaw`, `skills`, and `agent-hosts` trees are no longer part of the primary model.
4. A user can clone Skrya into an agent skill directory and have it work without first understanding the old asset-generation structure.
