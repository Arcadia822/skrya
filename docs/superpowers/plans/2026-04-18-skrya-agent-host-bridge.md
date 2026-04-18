# Skrya Agent Host Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-of-truth skill template system, host-aware asset generation, missing curation skills, and thin host prompt packs for Codex, Claude Code, and OpenClaw.

**Architecture:** Keep runtime topic logic in `skrya_orchestrator.intelligence`, and add a separate asset-builder layer for skill packaging. Author once under `skills-src/` and render checked-in assets for each supported host plus the workspace-native skill directory.

**Tech Stack:** Python 3.10, setuptools, unittest, Markdown, JSON, YAML

---

### Task 1: Add Failing Tests For Asset Generation

**Files:**
- Create: `D:\Documents\skrya\tests\test_agent_assets.py`
- Modify: `D:\Documents\skrya\tests\test_skill_contracts.py`

- [ ] Add a unit test that expects a builder to render all five core skills from source templates into the workspace skill root.
- [ ] Add a unit test that expects host-specific roots for Codex, Claude, and OpenClaw plus generated `skrya-lite/full/plan` prompt files.
- [ ] Add a CLI-level test or contract assertion that documents the `build-agent-assets` entrypoint and README guidance.
- [ ] Run the new tests to verify they fail before implementation.

### Task 2: Implement The Asset Builder

**Files:**
- Create: `D:\Documents\skrya\src\skrya_orchestrator\agent_assets.py`
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\main.py`
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\__init__.py`

- [ ] Add host config dataclasses and source template loaders.
- [ ] Implement markdown rendering, metadata emission, and prompt-pack rendering.
- [ ] Expose `build-agent-assets` from the CLI with `--host` support.
- [ ] Re-run the asset-builder tests and make them pass with the minimal implementation.

### Task 3: Add Skill Sources And Prompt Templates

**Files:**
- Create: `D:\Documents\skrya\skills-src\request-curation\skill.json`
- Create: `D:\Documents\skrya\skills-src\request-curation\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\skills-src\source-curation\skill.json`
- Create: `D:\Documents\skrya\skills-src\source-curation\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\skills-src\topic-curation\skill.json`
- Create: `D:\Documents\skrya\skills-src\topic-curation\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\skills-src\digest\skill.json`
- Create: `D:\Documents\skrya\skills-src\digest\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\skills-src\deep-analysis\skill.json`
- Create: `D:\Documents\skrya\skills-src\deep-analysis\SKILL.md.tmpl`
- Create: `D:\Documents\skrya\prompt-templates\skrya-lite.md.tmpl`
- Create: `D:\Documents\skrya\prompt-templates\skrya-full.md.tmpl`
- Create: `D:\Documents\skrya\prompt-templates\skrya-plan.md.tmpl`

- [ ] Move the current manually maintained skill language into `skills-src/`.
- [ ] Add the missing `request-curation` and `source-curation` source templates.
- [ ] Add thin prompt packs that define small-edit, full-execution, and planning-only behavior.

### Task 4: Generate Checked-In Assets

**Files:**
- Update generated outputs under: `D:\Documents\skrya\skills\`
- Create generated outputs under: `D:\Documents\skrya\.agents\skills\`
- Create generated outputs under: `D:\Documents\skrya\.claude\skills\`
- Create generated outputs under: `D:\Documents\skrya\.openclaw\skills\`
- Create generated outputs under: `D:\Documents\skrya\agent-hosts\`

- [ ] Run the builder against the repo root.
- [ ] Verify that generated outputs exist for all supported hosts.
- [ ] Keep workspace-facing `skills/` aligned with the new source templates.

### Task 5: Document The New Editing Model

**Files:**
- Modify: `D:\Documents\skrya\README.md`
- Modify: `D:\Documents\skrya\AGENTS.md`
- Modify: `D:\Documents\skrya\design\core-skills-spec.md`
- Modify: `D:\Documents\skrya\design\current-system-design.md`

- [ ] Document `skills-src/` as the source of truth.
- [ ] Document `build-agent-assets` as the regeneration command.
- [ ] Explain that `topic-curation` is the broad entrypoint, with `request-curation` and `source-curation` as narrower responsibilities.

### Task 6: Final Verification

**Files:**
- Read/scan only

- [ ] Run the full test suite with `python -m unittest discover -s tests -v`.
- [ ] Inspect generated directories to confirm expected host outputs are present.
- [ ] Report exactly what changed and any remaining limitations in the first-pass host bridge.

