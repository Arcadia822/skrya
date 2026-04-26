---
name: request-curation
description: Use when the user wants to refine what kinds of items matter within an existing topic, add or remove tracked angles, or turn digest feedback into durable brief rules. Trigger for Chinese feedback like "这条以后少推", "这类以后多推", "加上价格变化", or "别再推这种".
---
<!-- AUTO-GENERATED from request-curation/SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Request Curation

Translate user feedback about what should matter in a configured topic into durable request language.

Always resolve an explicit internal `topic-id` before reading or writing files, but do not ask nontechnical users for raw ids when a natural topic name can be mapped.

## Read First

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`

If the user is reacting to ranking or exclusions in a recent digest, also read:

- `topics/<topic-id>/digest.md`
- `runs/<topic-id>/latest-digest.md` when available
- `runs/<topic-id>/latest-digest-events.json` when available
- `runs/<topic-id>/ingest/latest-ingest.json` when available

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

## Use This Skill When

- the user wants to add a new tracked angle
- the user wants to narrow topic scope
- the user wants to exclude a class of items from future digests
- the user wants to rebalance what is ranked higher or lower
- the user points at one digest item as an example of what should or should not be surfaced again
- the user says "这个很重要"
- the user asks "为什么没有 ..." or reports a missed item

## Core Rule

Convert one-off user feedback into durable `brief.json` request language instead of copying the example literally.

## Missed Item Feedback

For "为什么没有 X", treat it as 漏报诊断 before editing anything:

- check latest digest for whether X was present under another wording
- check latest ingest artifact for whether X was collected but ranked out
- check source coverage and runtime retrieval query terms for whether X could be collected
- check ranking and exclusion rules for whether X was filtered or down-ranked
- propose the smallest durable change to `brief.json`, `digest.md`, or sources after explaining the likely failure point

## Required Behavior

1. Interpret the user request as a persistent preference, not a one-off chat reply.
2. Draft the smallest durable wording that captures that preference.
3. Show the proposed wording to the user in concise natural Chinese.
4. Confirm before writing any file.
5. Prefer updating `brief.json`.
6. Only touch `digest.md` if the requested change is really about ranking or exclusion policy rather than tracked angles.

## Output Rules

- Keep the conversation natural and short.
- Do not expose internal debug fields or config jargon unless needed.
- File names are internal execution details; do not show file names in normal user-facing replies unless the user asks for implementation details.
- Preserve the user's intent, but normalize the language into stable configuration text.

## Success Criteria

After this skill completes:

- `brief.json` reflects a durable tracking request
- one-off examples have been generalized into stable rules
- the user has explicitly confirmed the wording before it is written
