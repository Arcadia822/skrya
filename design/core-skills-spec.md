# Skrya Core Skills Spec

## Goal

Skrya organizes topic-driven work through five core bundled skills:

- `topic-curation`
- `request-curation`
- `source-curation`
- `digest`
- `deep-analysis`

The umbrella `skrya` skill exists to route requests into that topology.

## Global Rules

All bundled skills must follow these repository rules:

1. Topic-scoped work requires an explicit `topic-id`.
2. Prefer real data unless the task is explicitly about debugging sample flows.
3. Default user-facing output language is Chinese.
4. Hide source lists and internal debug metadata by default.
5. Preserve enough traceability to return sources later if the user asks.

## Skill Topology

### 1. Topic Entry Layer

`topic-curation` owns broad topic setup and iteration.

Use it when:

- the user does not have a configured `topic-id` yet
- the user says they want important information, tracking, or regular briefings about some company, industry, market, product category, or theme
- the user is still expressing topic intent in natural language

This skill must clarify intent before creating or changing durable topic files.

### 2. Configuration Layer

`request-curation` owns durable `brief.json` preference changes.

Use it when the topic already exists and the user wants to:

- add a tracked angle
- remove a tracked angle
- rebalance ranking preference
- exclude a class of items from future digests

`source-curation` owns durable `sources.json` changes after topic intent is already clear.

Use it when the user wants to add, remove, or refine sources for an existing topic and the confirmed briefing intent is already strong enough to judge source fit.

Current source feasibility rule:

- RSS means connectable
- no RSS means not connectable for now

### 3. Consumption Layer

`digest` turns a configured topic into a ranked numbered briefing.

Rules:

- every item is a single numbered paragraph
- no inline source list
- no special formatting for the top items
- end with a natural invitation to reply with a number

`deep-analysis` turns one digest item or one event reference into a deeper breakdown.

Rules:

- accept visible digest numbers
- resolve numbers against the latest digest for the same topic
- keep sources hidden by default but available on request

## Skill-Pack Packaging

Source of truth now follows this layout:

- `skill-pack.json` and `SKILL.md.tmpl` for the umbrella skill
- `<skill>/skill.json` and `<skill>/SKILL.md.tmpl` for bundled skills
- `prompt-templates/` for host prompt packs

Generated runtime docs are checked in beside their templates:

- `SKILL.md`
- `agents/openai.yaml`
- `<skill>/SKILL.md`
- `<skill>/agents/openai.yaml`

Generated host prompt artifacts are runtime-only:

- `.skrya/hosts/<host>/...`

They should be regenerated, not hand-edited.
