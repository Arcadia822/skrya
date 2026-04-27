# Skrya

> Topic-driven briefing workspace for agent-native daily digests, source curation, and event follow-up.

**Language:** [Chinese](README.md) | English

[![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
[![Agent Skill Pack](https://img.shields.io/badge/Agent_Skill_Pack-Skrya-0ea5e9.svg)](#skill-pack)
[![Tests](https://img.shields.io/badge/tests-unittest-10b981.svg)](#development)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Skrya turns natural-language tracking requests into durable briefing workflows. A user can say "Send me a daily briefing about BYD, new energy vehicles, and energy storage", and an agent should turn that into a confirmed topic, source plan, schedule, test run, daily digest, follow-up analysis, and durable feedback memory.

It is not a news app. It is the instruction, configuration, and runtime shape that lets agents operate a topic-driven briefing system without repeatedly rediscovering what the user meant. An excellent use of memory, at last.

## What Skrya Handles

| User need | Skrya behavior |
| --- | --- |
| "Send official domestic and international X news every morning" | Routes to topic setup before generic automation. |
| "What sources are configured?" | Proposes concrete source candidates before claiming the topic is configured. |
| "Run a test" | Produces a preview using the real digest template, without saving it by default. |
| "Why was today's briefing empty?" | Diagnoses generation, delivery, channel binding, and empty-send failure. |
| "Expand item 3" | Uses the latest digest index for deep analysis. |
| "Keep tracking this line" | Creates or updates a `thread` below the topic. |
| "Show fewer items like this" | Writes durable request preferences instead of treating feedback as disposable chat. |
| "Uninstall Skrya" | Offers skill-only, data-only, and complete uninstall modes. |

## Core Concepts

Skrya is topic-driven. The main durable entities are:

- `topic`: one long-running tracking area.
- `request`: user intent and ranking preferences inside a topic.
- `source`: confirmed retrieval source or provider-neutral runtime retrieval capability.
- `digest item`: a numbered event in a daily briefing.
- `thread`: a continuing timeline below a topic and above individual digest items.
- `channel`: an optional host conversation boundary used for delivery isolation.
- `template`: the output contract for setup, digest, test run, and analysis.

See [docs/domain-model.md](docs/domain-model.md) for the full entity map, including `channel`, `delivery context`, `automation`, `run`, `ingest artifact`, and `upgrade flow`.

## Language Policy

Skrya does not require an install-time language setting. Language is part of each topic's configuration:

- When a topic is created, default `topic.json.language` to the language the user used for topic creation.
- The user may explicitly request a different briefing output language for that topic.
- This project currently supports Chinese and English output. The schema and framework may remain extensible for more languages later.
- Topic language controls digest and deep-analysis output for that topic.
- When the user gives feedback later, the agent should converse in the language of that feedback. Do not change the topic output language unless the user explicitly asks.

## Skill Pack

The root `skrya` skill routes user intent to bundled skills:

| Skill | Purpose |
| --- | --- |
| `topic-curation` | Create or adjust a long-running topic. |
| `source-curation` | Confirm source candidates and runtime retrieval capabilities. |
| `request-curation` | Convert digest feedback into durable topic preferences. |
| `digest` | Generate ranked daily briefings with traceable sources. |
| `deep-analysis` | Expand one digest item or event into a concise analysis. |

Important workflow rules:

- Topic-scoped work resolves an internal `topic-id` before file operations.
- Recurring tracking is not satisfied by one-off chat research.
- Source candidates are proposed and confirmed before recurring delivery is declared configured.
- Channel-aware hosts bind scheduled delivery and resend to the creating channel by default.
- Test runs use the real digest template and do not append saved-file notes.
- Topical scheduled news pushes route to Skrya before generic reminders.

## User Journey

Typical setup:

1. User describes a tracking need in natural language.
2. Agent confirms the durable topic intent.
3. Agent proposes concrete sources and marks what can be automatically connected.
4. User confirms the source plan.
5. Agent creates or proposes the recurring automation for the current channel when the host supports it.
6. Agent asks whether to run one test digest.
7. Future `A` / `B` / `C` feedback updates analysis, threads, or preferences.

Example prompts:

```text
Send me a daily briefing about important AI browser developments.
```

```text
Keep tracking the BYD flash-charging rollout thread and continue it when new developments appear.
```

```text
Expand item 3 and tell me whether it is still worth watching.
```

## Digest Format

Daily digest output uses one stable template: title, optional thread updates, uniform line boxes, compact source references, then `## System`.

```markdown
# 2026-04-26 | New Energy Vehicles | Daily Briefing

## Thread Updates

┌─ **【thread】BYD flash-charging rollout**
│ The thread has moved from launch claims to execution, with attention shifting
│ to whether stations are actually coming online.
│
│ Watch next: first live cities; repeatable real-world charging performance.
└

## Today's Briefs

┌─ **【Brief 1】First BYD flash-charging cities start to become clear**
│ This has moved from product demonstration to concrete station rollout and
│ city coverage.
│
│ Sources: [example.com](https://example.com/byd-flash-charge-cities)
└

---

## System

- Execution time: 2026-04-26 12:19 (Asia/Shanghai)
- Status: Complete: generated 3 brief items and updated 1 thread.
- Scan window: last 24 hours (default)
- Skrya: 0.1.0
- Available follow-ups:
  - A. Deep-analyze specified brief items, for example: `A 3 5 12`.
  - B. Create a new thread, for example: `B 3 4 5 keep tracking`.
  - C. Adjust briefing and thread strategy, for example: `C 6 7 I dislike this; skip xxx next time`.
```

The system section includes the Skrya version. Agent framework/version and LLM model are included only when the host exposes them.

## Runtime Data

User topic data lives under the Skrya data root, not necessarily inside this repository.

Defaults:

- Normal desktop hosts: `~/.skrya`
- OpenClaw/container-style mounted workspaces: `.skrya/data`
- Override: `SKRYA_DATA_ROOT` or `--data-root`

Topic files:

```text
<skrya-data-root>/topics/<topic-id>/
  topic.json
  brief.json
  sources.json
  digest.md
  deep-analysis.md
  thread-seeds.json
```

Runtime artifacts:

```text
<skrya-data-root>/runs/<topic-id>/
  latest-digest.md
  latest-digest-events.json
  ingest/latest-ingest.json
  threads/latest-threads.json
```

Concrete thread paths for the fixture topic:

```text
<skrya-data-root>/topics/new-energy-vehicles/thread-seeds.json
<skrya-data-root>/runs/new-energy-vehicles/threads/latest-threads.json
```

`thread` details are documented in [docs/threads.md](docs/threads.md). The fixture topic is [topics/new-energy-vehicles/](topics/new-energy-vehicles/), including `thread-seeds.json`. A timeline can be replayed with:

```bash
python3 -m skrya_orchestrator.main thread --topic new-energy-vehicles --thread "byd-flash-charge" --root . --data-root .
```

The full example flow is in [docs/user-journeys.md](docs/user-journeys.md), especially journey 6 for continuing thread tracking.

## Retrieval

Skrya can use third-party retrieval tools without making them durable dependencies. Long-term source configuration stores capabilities, not provider names:

- `web_search`
- `news_search`
- `site_search`
- `social_search`
- `document_fetch`

Provider output should be normalized into `skrya.ingest.v1`; digest and deep analysis consume normalized artifacts, not raw retrieval dumps. See [docs/external-retrieval-interface.md](docs/external-retrieval-interface.md).

## Installation

Requirements: Python 3.10+.

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

Install the skill pack:

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

Host-specific installs:

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host codex
python3 -m skrya_orchestrator.main install-skill-pack --root . --host claude
python3 -m skrya_orchestrator.main install-skill-pack --root . --host openclaw
```

Convenience scripts:

```bash
./setup --host auto
./setup --host openclaw --data-root-mode workspace --migrate-data
```

PowerShell:

```powershell
./setup.ps1 --host auto
```

Manage the data root:

```bash
python3 -m skrya_orchestrator.main data-root --root .
python3 -m skrya_orchestrator.main data-root --root . --set .skrya/data --scope workspace --migrate
```

`--migrate` and `--migrate-data` copy existing workspace `topics/` and `runs/` into the configured data root without deleting the old files.

## Uninstall

Skrya supports three uninstall modes. An agent should explain these choices and confirm the destructive ones before acting.

| Mode | What it removes | What it keeps |
| --- | --- | --- |
| `skills-keep-data` | Installed Skrya skill directories and bundled skill links | Topic config, run history, data-root config |
| `data-keep-skills` | Skrya data root and data-root config | Installed skills |
| `complete` | Skills, Skrya data/config, and marked Skrya routing notes in global instruction files such as `AGENTS.md` | Unrelated user instructions and non-Skrya data |

Commands:

```bash
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode skills-keep-data
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode data-keep-skills
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode complete
```

Complete uninstall removes only Skrya routing notes from global instruction memory. Marked blocks such as `SKRYA-ROUTING-NOTE` are safe to remove automatically; unrelated `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, or `tools.md` content must be preserved.

## Upgrade

Read [docs/upgrade.md](docs/upgrade.md) before updating an existing install.

Common flow:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main version --root . --check-latest
git pull --ff-only
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-thread-naming
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
PYTHONPATH=src python3 -m unittest discover -s tests
```

Current upgrade support includes migration from legacy `event-thread` runtime naming to `thread` naming. Old files are left in place for audit and rollback, because deleting evidence during migration would be a charmingly avoidable mistake.

## CLI Reference

Examples below use `--data-root .` to run against checked-in fixtures. Real installs usually read from `~/.skrya`.

```bash
python3 -m skrya_orchestrator.main digest --topic new-energy-vehicles --root . --data-root . --sample
python3 -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root . --data-root .
python3 -m skrya_orchestrator.main thread --topic new-energy-vehicles --thread "byd-flash-charge" --root . --data-root .
python3 -m skrya_orchestrator.main refresh-threads --topic new-energy-vehicles --root . --data-root .
python3 -m skrya_orchestrator.main retrieval-request --topic k-entertainment --root . --data-root .
python3 -m skrya_orchestrator.main ingest --topic k-entertainment --root . --data-root . --file runs/k-entertainment/ingest/input.json
python3 -m skrya_orchestrator.main version --root . --check-latest
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode skills-keep-data
```

## Repository Layout

```text
.
  skill-pack.json
  SKILL.md.tmpl
  SKILL.md
  agents/openai.yaml

  topic-curation/
  request-curation/
  source-curation/
  digest/
  deep-analysis/

  prompt-templates/
  topics/new-energy-vehicles/
  docs/
  design/
  src/skrya_orchestrator/
  tests/
```

## Source Of Truth

For agent-facing behavior, edit source templates first:

1. Root skill: `skill-pack.json` and `SKILL.md.tmpl`
2. Bundled skills: `<skill>/skill.json` and `<skill>/SKILL.md.tmpl`
3. Host prompts: `prompt-templates/`
4. Build artifacts:

```bash
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

Generated `SKILL.md` files and `agents/openai.yaml` files are checked in so the repository can be installed directly as a skill pack. `.skrya/hosts/`, `.skrya/data/`, `runs/`, `tmp/`, `__pycache__/`, and `*.egg-info/` are runtime or cache output.

## Development

```bash
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests
```

Tests cover skill-pack generation, topic resolution, digest formatting, source curation behavior, runtime retrieval, ingest normalization, thread timelines, upgrades, and skill documentation contracts.

Contribution guidelines are in [CONTRIBUTING.md](CONTRIBUTING.md). The license is [MIT](LICENSE).
