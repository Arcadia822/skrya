---
name: digest
description: Use when the user wants a ranked daily briefing for a configured topic, asks what matters today for that topic, or wants a chat-friendly digest without inline source lists. Trigger for Chinese requests like "今天有什么重要", "给我今日简报", "跑一次日报", or "看看这个主题今天发生了什么".
---
<!-- AUTO-GENERATED from digest/SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Digest

Generate a topic-level digest for a resolved Skrya topic.

Always resolve an explicit internal `topic-id` before reading files, but do not ask nontechnical users for raw ids when a natural topic name can be mapped.

## Read First

Read these files before drafting the digest:

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`
- `topics/<topic-id>/sources.json`
- `topics/<topic-id>/digest.md`

If available, also read the latest event candidates or prior digest artifacts for that topic.
When runtime retrieval was used, consume only normalized `skrya.ingest.v1` artifacts under `runs/<topic-id>/ingest/`. Do not consume raw provider output directly.
When event-thread seeds exist, use them to surface continuing event-line updates and preserve durable topic memory.

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

## Output Rules

- The top-level title must include the execution date and visible topic name: `# YYYY-MM-DD｜主题名｜每日简报`.
- Treat events as the primary unit, not articles.
- Show concise source references in a separate source line for every digest item.
- Do not show internal debug fields such as matched request ids.
- Fold ranking judgment into natural prose. Avoid rigid labels such as "why it matters".
- Render every event as a lightweight line box with the visible number and title merged into the first line:
  ```markdown
  ┌─ **【简讯1】事件标题**
  │ 一句判断或摘要。
  │ 可以继续换行补充判断。
  │
  │ 信源：[来源名](url) [来源名](url)
  └
  ```
- Keep the tone concise, calm, and readable in chat.
- Save the digest to the workspace run directory.
- File names are internal execution details; do not show file names in normal user-facing replies unless the user asks for implementation details.
- After the digest body, add a horizontal divider `---`, then a `## 系统提示` section.
- The system prompt section must include execution time, execution status, scan time range, and available follow-up operations.
- Put feedback choices inside `## 系统提示`: `A <numbers>` for deep analysis, `B <numbers> <name/intent>` for event-thread creation or updates, and `C <numbers/reason>` for durable topic memory changes.

## Required Behavior

1. Load topic configuration and topic-specific digest guidance.
2. Consume the available normalized `skrya.ingest.v1` items or event candidates.
3. Remove obvious duplicates and low-value fragments.
4. Rank events using the topic brief and digest standard.
5. Write every event as a compact line box with stable visible numbers in the first line and source references after a blank separator line.
6. Keep the format uniform from the first item to the last.
7. Save the digest markdown file under `runs/<topic-id>/latest-digest.md`.
8. Preserve enough traceability so that if the user later asks for the source of an item, you can return the complete corresponding sources.
9. If a seeded event-thread matches today’s items, write a concise line-box event-line update before the normal numbered items. Do not include a "today matched digest items" line in the event-line update.
10. End the digest body, insert `---`, and write a `## 系统提示` section with execution metadata and A/B/C feedback options.

## Feedback Handling

- `A <numbers>` routes the selected digest items to deep analysis.
- `B <numbers> <name/intent>` means the user wants a continuing event line; propose a stable event-thread seed before writing it.
- `C <numbers/reason>` means the user is adjusting durable topic memory; route to request curation instead of answering only in chat.
- If the user asks "为什么没有 X", do not regenerate blindly; start missed-item diagnosis through request curation.
- If the user says "这个很重要", treat it as a durable ranking or watchpoint update, not a compliment to the current answer.

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

## Source Display

Default digest output should show compact source references on a separate source line inside each line box. Use human-readable source labels when available, or the domain name for URL-only sources. If the user asks where a digest item came from, answer with the complete relevant sources for that item.
