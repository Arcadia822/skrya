---
name: digest
description: Use when the user wants a ranked daily briefing for a configured topic, asks what matters today for that topic, or wants a chat-friendly digest without inline source lists. Trigger for Chinese requests like "今天有什么重要", "给我今日简报", "跑一次日报", or "看看这个主题今天发生了什么".
---
<!-- AUTO-GENERATED from digest/SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Digest

Generate a topic-level digest for a resolved Skrya topic.

Always resolve an explicit internal `topic-id` before reading files, but do not ask nontechnical users for raw ids when a natural topic name can be mapped.
Before reading or writing topic files, resolve the Skrya data root. Topic configuration and generated artifacts live under `<skrya-data-root>/`, not necessarily under the skill repository.

## Read First

Read these files before drafting the digest:

- `<skrya-data-root>/topics/<topic-id>/topic.json`
- `<skrya-data-root>/topics/<topic-id>/brief.json`
- `<skrya-data-root>/topics/<topic-id>/sources.json`
- `<skrya-data-root>/topics/<topic-id>/digest.md`
- topic-specific digest template file when configured; otherwise `digest/templates/default-digest.md`

If available, also read the latest event candidates or prior digest artifacts for that topic.
When runtime retrieval was used, consume only normalized `skrya.ingest.v1` artifacts under `<skrya-data-root>/runs/<topic-id>/ingest/`. Do not consume raw provider output directly.
When thread seeds exist, use them to surface continuing thread updates and preserve durable topic memory. Every thread whose effective status is `active` must be visible in the digest even when the current scan finds no verified increment.

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

If the user asks to create or update the topic-specific digest template itself, route to `topic-curation` and use its template-update notice and pre-save validation gate. Do not overwrite an existing template with an unchecked candidate.

## Delivery Context

Digest generation and digest delivery are separate steps.

- Before scheduled delivery, manual resend, or "why was today's digest empty" diagnosis, resolve the topic. In channel-aware hosts, also resolve the channel/conversation binding for the current request.
- In channel-aware hosts, only send the digest bound to the current channel/conversation unless the user explicitly names another target and the host supports cross-channel delivery.
- In channel-aware hosts, treat the current channel/conversation as the default visibility boundary. Resolve against `delivery-bindings.json` first; do not scan all topics or all generated digests from the current channel.
- If no topic is bound to the current channel/conversation, ask which topic the user means or explain that no binding was found. Do not resend, combine, or repair every topic.
- In hosts without channel/conversation concepts, fall back to the resolved topic, user intent, and available automation context.
- If multiple same-channel topics are plausible in a channel-aware host, ask the user which digest they mean instead of sending all generated digests.
- Do not bundle unrelated topic digests from other channels into a resend response, even when they share a scheduled run time.
- If generated content exists but the delivered message was empty, resend via the explicit message tool when available and verify that the sent body is non-empty.

## Output Rules

- Use the topic's configured output language from `topic.json.language`. Supported output languages are Chinese and English; keep the template model extensible for future languages.
- Use the configured digest template file as writing and reference guidance for the digest layout. Do not reconstruct the report shape from memory when a template file is available.
- Treat `digest.md` as ranking, exclusion, and judgment guidance; it is not the output format template.
- Do not derive digest language from install-time settings. Installation is language-neutral.
- The top-level title must include the execution date and visible topic name. Chinese format: `# YYYY-MM-DD｜主题名｜每日简报`. English format: `# YYYY-MM-DD | Topic Name | Daily Briefing`.
- Treat events as the primary unit, not articles.
- Show concise source references in a separate source line for every digest item.
- Do not show internal debug fields such as matched request ids.
- Fold ranking judgment into natural prose. Avoid rigid labels such as "why it matters".
- Write every event as a lightweight line box with the visible number and title merged into the first line:
  ```markdown
  ┌─ **【简讯1】事件标题**
  │ 一句判断或摘要。
  │ 可以继续换行补充判断。
  │
  │ 信源：[来源名](url) [来源名](url)
  └
  ```
- Keep the tone concise, calm, and readable in chat.
- If `thread-seeds.json` or the latest thread runtime artifact contains any `status=active` thread, add a dedicated `## 事件线时间线更新` section (`## Event Timeline Updates` for English topics) before the normal digest items.
- For every active thread, show its name and ID, today's verified increment, its position relative to the latest known timeline state, an impact judgment, and the next observation point.
- When an active thread has no verified increment in the current scan window, do not omit it. Show an explicit review result and the latest known timeline state (latest timeline date, headline, and concise summary when available), followed by the next observation point.
- Save scheduled or user-requested real digests to the Skrya data root run directory with an absolute execution-time filename such as `digest-YYYYMMDDTHHMMSS+0800.md`.
- Keep `latest-digest.md` as a symlink or pointer to the newest real digest artifact; do not treat it as the canonical digest filename.
- For test runs, use the same digest template in chat only and do not save a timestamped artifact or update `latest-digest.md` unless the user explicitly asks to save the preview.
- File names are internal execution details; do not show file names in normal user-facing replies unless the user asks for implementation details.
- After the digest body, add a horizontal divider `---`, then a system section in the topic language: `## 系统提示` for Chinese or `## System` for English.
- The system section must include execution time, execution status, scan time range, current Skrya version, and available follow-up operations.
- Include the agent framework/version and LLM model only when the host exposes them; silently omit unknown fields.
- When the host can inspect the Skrya repository, check the latest visible Skrya version or upstream revision. If a newer version is available, ask the user whether to update and follow `docs/upgrade.md`.
- Put feedback choices inside the system section and explain them in the topic language: `dig: <numbers>` for deep analysis, `track: <numbers> <name/intent>` for thread creation or updates, and plain-language preference feedback for durable topic memory changes.
- Do not put chatty prefaces before the digest body.
- Do not append implementation notes such as saved file paths after the `## 系统提示` section.
- For a test run, the first visible line must be the digest title. Do not write "我先跑一下", "测试结果如下", saved-file notes, or any other prose before or after the templated digest.

## Required Behavior

1. Load topic configuration, topic-specific digest guidance, and the digest template file.
2. Consume the available normalized `skrya.ingest.v1` items or event candidates.
3. Remove obvious duplicates and low-value fragments.
4. Rank events using the topic brief and digest standard.
5. Write every event as a compact line box with stable visible numbers in the first line and source references after a blank separator line.
6. Keep the format uniform from the first item to the last.
7. Save the digest markdown file under `<skrya-data-root>/runs/<topic-id>/` with an absolute execution-time filename only for scheduled or user-requested real digests; then update `latest-digest.md` as a symlink or pointer to that file. Do not save test-run previews by default.
8. Preserve enough traceability so that if the user later asks for the source of an item, you can return the complete corresponding sources.
9. Resolve all effective `status=active` threads from `thread-seeds.json` and the latest runtime thread artifact. Always write a line-box entry for every active thread in the dedicated event-timeline section before the normal numbered items.
10. For an active thread with verified new items, include the thread name/ID, today's increment, the previous timeline position it continues from, impact judgment, and next observation. For an active thread without a verified increment, explicitly state that the current scan found no verified update and show its latest known timeline state plus the next observation. Never suppress an active thread merely because a generic "no material update" rule applies.
11. End the digest body, insert `---`, and write a `## 系统提示` section with execution metadata, `dig:` / `track:` options, and a plain-language preference feedback option.
12. For a test run, still use the same digest template and `## 系统提示` format, mark execution status as test/preview, explain `dig: <编号>`, `track: <编号> <名称/意图>`, and plain-language preference feedback, and do not mention saved artifacts.

## Feedback Handling

- `dig: <numbers>` routes the selected digest items to deep analysis.
- `track: <numbers> <name/intent>` means the user wants a continuing thread; propose a stable thread seed before writing it.
- Plain-language preference feedback means the user is adjusting durable topic memory; route to request curation instead of answering only in chat.
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
