---
name: digest
description: Use when the user wants a ranked daily briefing for a configured topic, asks what matters today for that topic, or wants a chat-friendly digest without inline source lists.
---
# Digest

Generate a topic-level digest for a specific `topic-id`.

Always require an explicit `topic-id`.

## Read First

Read these files before drafting the digest:

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`
- `topics/<topic-id>/sources.json`
- `topics/<topic-id>/digest.md`

If available, also read the latest event candidates or prior digest artifacts for that topic.

Also inherit any applicable workspace defaults from `CLAUDE.md`.

## Output Rules

- Treat events as the primary unit, not articles.
- Do not show source lists in the normal digest output.
- Do not show internal debug fields such as matched request ids.
- Fold ranking judgment into natural prose. Avoid labels like "why it matters:" or similarly rigid template markers.
- Do not use section titles like `Top 5 必看`, `今日观察`, or `建议深挖`.
- Render every event as a numbered single paragraph so the user can reply with a number to request deeper analysis.
- Keep the tone concise, calm, and readable in chat or Feishu.
- Save the digest to the workspace run directory.
- End with a natural sentence that tells the user they can reply with a number to continue, without exposing internal skill names.

## Required Behavior

1. Load topic configuration and topic-specific digest guidance.
2. Consume the available normalized items or event candidates.
3. Remove obvious duplicates and low-value fragments.
4. Rank events using the topic brief and digest standard.
5. Write every event as a single-paragraph numbered item with stable visible numbers.
6. Keep the format uniform from the first item to the last.
7. Save the digest markdown file under `runs/<topic-id>/latest-digest.md`.
8. Preserve enough traceability so that if the user later asks for the source of an item, you can return the corresponding sources.
9. End with a natural follow-up line that invites the user to reply with a number for deeper analysis.

## Ranking Heuristics

Prefer events that:

- strongly match the topic brief
- have multiple independent supporting sources
- are clearly heating up
- have real event shape rather than isolated chatter

Down-rank events that:

- are obvious rehashes with no new movement
- rely mostly on weak or unverifiable sources
- are noisy fragments without clear event value

## Structure

Use this shape by default:

1. A numbered list of events
2. Each item is one compact paragraph with the title folded into the opening clause

Do not add a separate "deep dive suggestions" section. The numbering itself is the handoff surface for continuing into deeper analysis.

## Source Follow-up

If the user asks where a digest item came from, answer with the relevant sources for that item. Keep source disclosure on-demand, not inline by default.

## Notes

For fuller design intent, see:

- `design/digest-spec.md`
- `design/core-skills-spec.md`
