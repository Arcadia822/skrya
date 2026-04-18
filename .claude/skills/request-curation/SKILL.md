---
name: request-curation
description: Use when the user wants to refine what kinds of items matter within an existing topic, add or remove tracked angles, or turn digest feedback into durable brief rules.
---
# Request Curation

Translate user feedback about what should matter in a configured topic into durable request language.

Always require an explicit `topic-id`.

## Read First

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`

If the user is reacting to ranking or exclusions in a recent digest, also read:

- `topics/<topic-id>/digest.md`
- `runs/<topic-id>/latest-digest.md` when available

Also inherit any applicable workspace defaults from `CLAUDE.md`.

## Use This Skill When

- the user wants to add a new tracked angle
- the user wants to narrow topic scope
- the user wants to exclude a class of items from future digests
- the user wants to rebalance what is ranked higher or lower
- the user points at one digest item as an example of what should or should not be surfaced again

## Core Rule

把用户的一次性反馈改写成可持续执行的 `brief.json` 请求语言，而不是把例子原样抄进去。

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
- Preserve the user's intent, but normalize the language into stable configuration text.

## Success Criteria

After this skill completes:

- `brief.json` reflects a durable tracking request
- one-off examples have been generalized into stable rules
- the user has explicitly confirmed the wording before it is written
