# Remove Plane And Symphony Cleanup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Plane/Symphony from the repo, restore a topic-driven briefing narrative, repair visible UTF-8 corruption, and tighten skill descriptions so they only describe trigger conditions.

**Architecture:** Keep the topic briefing path centered on `skrya_orchestrator.intelligence` plus the topic config directories under `topics/`. Delete the orchestration layer, Plane/Symphony skills and infra, and stale generated artifacts. Rewrite top-level docs so the repo presents as a topic-driven workspace first.

**Tech Stack:** Python 3.10, setuptools, unittest, Markdown, JSON

---

### Task 1: Rewrite Repository Narrative

**Files:**
- Modify: `D:\Documents\skrya\README.md`
- Modify: `D:\Documents\skrya\pyproject.toml`
- Create or update: `D:\Documents\skrya\docs\superpowers\specs\2026-04-18-remove-plane-symphony-design.md`

- [ ] Rewrite `README.md` so the first screen describes a topic-driven briefing workspace, the topic file layout, the digest/deep-analysis workflow, and the surviving CLI entrypoints.
- [ ] Remove Plane/Symphony setup text, Docker instructions, and obsolete workflow references from `README.md`.
- [ ] Update `pyproject.toml` package description so it no longer calls the project a Plane/Symphony orchestrator.

### Task 2: Remove Plane/Symphony Product Surface

**Files:**
- Delete: `D:\Documents\skrya\infra\plane\`
- Delete: `D:\Documents\skrya\skills\plane-api\`
- Delete: `D:\Documents\skrya\skills\plane-symphony\`
- Delete: `D:\Documents\skrya\WORKFLOW.md`
- Delete: `D:\Documents\skrya\runs\symphony\`
- Delete: `D:\Documents\skrya\tmp\plane-src\`

- [ ] Delete all first-party Plane/Symphony infra, skill directories, workflow contracts, generated runs, and temp source trees.
- [ ] Remove any top-level ignore rules or metadata entries that only exist for deleted Plane/Symphony paths.

### Task 3: Trim The Python Package To Topic Briefing

**Files:**
- Modify: `D:\Documents\skrya\src\skrya_orchestrator\main.py`
- Keep: `D:\Documents\skrya\src\skrya_orchestrator\intelligence.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\agent_runner.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\config.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\http_transport.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\models.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\plane_client.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\service.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\session_launcher.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\workflow.py`
- Delete: `D:\Documents\skrya\src\skrya_orchestrator\workspace_manager.py`

- [ ] Simplify `main.py` so it only exposes digest- and deep-analysis-related commands.
- [ ] Remove imports and code paths that require `AppConfig`, `OrchestratorService`, Plane clients, or workflow state.
- [ ] Delete the Python modules that only exist for Plane/Symphony orchestration.

### Task 4: Repair Skills And Design Docs

**Files:**
- Modify: `D:\Documents\skrya\skills\digest\SKILL.md`
- Modify: `D:\Documents\skrya\skills\deep-analysis\SKILL.md`
- Modify: `D:\Documents\skrya\skills\topic-curation\SKILL.md`
- Modify or rewrite: `D:\Documents\skrya\design\agent-native-intelligence-system-design.md`
- Modify or rewrite: `D:\Documents\skrya\design\core-skills-spec.md`
- Modify or rewrite: `D:\Documents\skrya\design\current-system-design.md`
- Modify or rewrite: `D:\Documents\skrya\design\deep-analysis-spec.md`
- Modify or rewrite: `D:\Documents\skrya\design\digest-spec.md`
- Modify or rewrite: `D:\Documents\skrya\design\k-entertainment-deep-analysis-sample.md`
- Modify or rewrite: `D:\Documents\skrya\design\k-entertainment-digest-sample.md`
- Modify or rewrite: `D:\Documents\skrya\design\k-entertainment-topic-instance.md`
- Modify or rewrite: `D:\Documents\skrya\design\thread-record-2026-04-12.md`
- Modify or rewrite: `D:\Documents\skrya\design\topic-template-spec.md`

- [ ] Update surviving skill descriptions so they only describe when the skill should be invoked, not the workflow.
- [ ] Rewrite corrupted Chinese passages in `topic-curation` so the skill reads naturally and keeps the same intent.
- [ ] Repair visible UTF-8 corruption in the design documents so they are readable again and aligned with the topic-driven system.

### Task 5: Align Tests With The Surviving System

**Files:**
- Modify: `D:\Documents\skrya\tests\test_skill_contracts.py`
- Modify: `D:\Documents\skrya\tests\test_intelligence.py`
- Modify: `D:\Documents\skrya\tests\test_main_intelligence.py`
- Delete: `D:\Documents\skrya\tests\test_config.py`
- Delete: `D:\Documents\skrya\tests\test_models.py`
- Delete: `D:\Documents\skrya\tests\test_plane_api_skill_script.py`
- Delete: `D:\Documents\skrya\tests\test_plane_client.py`
- Delete: `D:\Documents\skrya\tests\test_session_launcher.py`
- Delete: `D:\Documents\skrya\tests\test_workflow.py`

- [ ] Remove tests that only validate deleted Plane/Symphony code.
- [ ] Update surviving intelligence and skill contract tests to assert readable Chinese text instead of corrupted byte-decoded fragments.
- [ ] Keep the surviving tests focused on digest/deep-analysis behavior and topic-curation contract guarantees.

### Task 6: Verify Cleanup

**Files:**
- Read/scan only

- [ ] Run a repository text scan for `plane`, `Plane`, `symphony`, and `Symphony` and inspect leftovers.
- [ ] Run targeted tests for the surviving topic briefing system.
- [ ] Summarize any intentional residual references that remain after cleanup.

