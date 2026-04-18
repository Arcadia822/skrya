# Skrya Installable Skill Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Skrya into a repository-native installable skill pack with an umbrella skill, bundled root-level skills, runtime host prompt artifacts, and a global installer.

**Architecture:** Keep digest and deep-analysis runtime logic in `skrya_orchestrator.intelligence`, but move agent-facing packaging to a repository-native layout. Generate checked-in runtime `SKILL.md` and `agents/openai.yaml` files in place, and move host prompt artifacts into `.skrya/hosts/`.

**Tech Stack:** Python 3.10, setuptools, unittest, Markdown, JSON, YAML

---

### Task 1: Introduce The Repository-Native Skill Pack Layout

**Files:**
- Create: `D:\Documents\skrya\skill-pack.json`
- Create: `D:\Documents\skrya\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\<skill>/skill.json`
- Create: `D:\Documents\skrya\<skill>/SKILL.md.tmpl`

- [ ] Add umbrella skill metadata and template at the repository root.
- [ ] Move bundled skill source-of-truth into root-level skill directories.
- [ ] Remove the old `skills-src/`-centric authoring model.

### Task 2: Replace The Asset Builder With A Skill-Pack Builder

**Files:**
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\agent_assets.py`
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\main.py`
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\__init__.py`

- [ ] Generate root and bundled runtime `SKILL.md` files in place.
- [ ] Generate `agents/openai.yaml` metadata in place.
- [ ] Generate host prompt artifacts under `.skrya/hosts/`.
- [ ] Keep `build-agent-assets` as an alias for `build-skill-pack`.

### Task 3: Add Installation Entry Points

**Files:**
- Create: `D:\Documents\skrya\setup`
- Create: `D:\Documents\skrya\setup.ps1`
- Modify: `D:\Documents\skrya\pyproject.toml`

- [ ] Add `install-skill-pack`.
- [ ] Add a root `setup` wrapper for direct installation.
- [ ] Expose a console entry point.

### Task 4: Update Documentation And Contracts

**Files:**
- Modify: `D:\Documents\skrya\README.md`
- Modify: `D:\Documents\skrya\AGENTS.md`
- Modify: `D:\Documents\skrya\design\current-system-design.md`
- Modify: `D:\Documents\skrya\design\core-skills-spec.md`
- Modify: `D:\Documents\skrya\tests\test_agent_assets.py`
- Modify: `D:\Documents\skrya\tests\test_skill_contracts.py`

- [ ] Document the installable skill-pack layout.
- [ ] Document the new build and install commands.
- [ ] Update test expectations to the new directory model.

### Task 5: Remove The Old Checked-In Generated Trees

**Files:**
- Delete: `D:\Documents\skrya\skills-src\`
- Delete: `D:\Documents\skrya\skills\`
- Delete: `D:\Documents\skrya\.agents\`
- Delete: `D:\Documents\skrya\.claude\`
- Delete: `D:\Documents\skrya\.openclaw\`
- Delete: `D:\Documents\skrya\agent-hosts\`

- [ ] Remove the obsolete checked-in generation targets so the repository does not present two competing skill-pack models.

### Task 6: Verify The New Model

**Files:**
- Read/scan only

- [ ] Run `python -m skrya_orchestrator.main build-skill-pack --root . --host all`.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Confirm that root and bundled generated skill docs exist and `.skrya/hosts/` is runtime-only.
