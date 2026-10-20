---
name: digest
description: Use when the user wants a ranked daily briefing for a configured topic, asks what matters today for that topic, or wants a chat-friendly digest with compact source references. Trigger for Chinese requests like "今天有什么重要", "给我今日简报", "跑一次日报", or "看看这个主题今天发生了什么".
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
When runtime retrieval was used, consume only normalized `skrya.ingest.v2` artifacts under `<skrya-data-root>/runs/<topic-id>/ingest/`. Do not consume raw provider output directly.
When thread seeds exist, use them to surface continuing thread updates and preserve durable topic memory. Every thread whose effective status is `active` must be visible in the digest even when the current scan finds no verified increment.

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

If the user asks to create or update the topic-specific digest template itself, route to `topic-curation`. Use its separate create/update drafting flows and the shared candidate-only validation and save gate. Do not read an existing topic template as the basis for create, and do not create or overwrite a target with an unchecked candidate.

## Delivery Context

Digest generation and digest delivery are separate steps.

- Before scheduled delivery, manual resend, or "why was today's digest empty" diagnosis, resolve the topic. In channel-aware hosts, also resolve the channel/conversation binding for the current request.
- In channel-aware hosts, only send the digest bound to the current channel/conversation unless the user explicitly names another target and the host supports cross-channel delivery.
- In channel-aware hosts, treat the current channel/conversation as the default visibility boundary. Resolve against `delivery-bindings.json` first; do not scan all topics or all generated digests from the current channel.
- If no topic is bound to the current channel/conversation, ask which topic the user means or explain that no binding was found. Do not resend, combine, or repair every topic.
- In hosts without channel/conversation concepts, fall back to the resolved topic, user intent, and available automation context.
- If multiple same-channel topics are plausible in a channel-aware host, ask the user which digest they mean instead of sending all generated digests.
- Do not bundle unrelated topic digests from other channels into a resend response, even when they share a scheduled run time.
- For Feishu, use the native `skrya deliver` command with an explicit bound target, not a generic text sender. Do not claim delivery from file creation or token acquisition alone.

## Output Rules

- Use the topic's configured output language from `topic.json.language`. Supported output languages are Chinese and English; keep the template model extensible for future languages.
- Use the configured digest template file as writing and reference guidance for the digest layout. Do not reconstruct the report shape from memory when a template file is available.
- Treat `digest.md` as ranking, exclusion, and judgment guidance; it is not the output format template.
- Do not derive digest language from install-time settings. Installation is language-neutral.
- The title includes execution date and topic name. Preserve the actual scan interval near the title, not as an execution log.
- Treat events as the primary unit, not articles. Show N-xx references and a source line for each item.
- When collected source health reports a real problem for enabled sources, add one concise lead line before the first section naming the affected sources and the pending neutral retrieval handoff. This is part of the scan summary, not a sixth action; the trailing action list stays exactly five.
- Use plain Markdown headings and paragraphs, never decorative line boxes or tab alignment. Native Feishu rendering adds the approved Schema 2.0 colors, badges and two-column title/date rows.
- Keep facts concise when writing, approximately three lines, and judgment approximately two lines. Do not truncate collected facts or remove news to fit a card.
- Include every effective active Thread before news. Show a T-xx reference and name, not the internal thread ID.
- Latest developments retain each verified news item separately, with title link, genuine date, facts and comment, including associated N-xx references.
- The historical display selects curated important milestones across the complete lifecycle. Agent-authored `milestone_reason` is required. A restored `milestone_date` also records `milestone_date_basis`. Show only genuinely dated, sourced nodes; do not infer importance by keywords or the latest N records.
- Keep the full underlying timeline, all unknown fields and complete sources for dig and write. Merge and deduplicate without deleting old entries.
- With no verified update, keep the active Thread's latest known state and next observation. If historical curation is incomplete, say so rather than invent nodes.
- Save real digests as `digest-YYYYMMDDTHHMMSS+0800.md` with a frozen events.json sidecar. Keep `latest-digest.md` as a symlink or pointer.
- Test runs use the same digest template but stay in chat. Do not save previews or advance latest pointers unless explicitly asked. Previews read existing state without writing: they do not advance repeat-hiding memory, source generations, source health records, or caches.
- End with `---` and `## 可继续操作`, or `## Available actions` for English. Include exactly `dig: N-01`, `track: N-02`, `dig: T-01`, `write: T-01`, and natural-language feedback, explained in the topic language.
- Keep model, framework, version, execution logs, delivery conclusions and file paths out of user output. Record operational information separately.
- When upgrading, use `docs/upgrade.md` and keep each host's data, credentials, targets and schedule unchanged.
- Do not put chatty prefaces before the digest body.
- Do not append implementation notes or saved file paths after the actions section.
- For a test run, the first visible line must be the digest title. Do not write "我先跑一下", "测试结果如下", saved-file notes, or any other prose before or after the templated digest.

## Required Behavior

1. Load topic configuration, topic-specific digest guidance, and the digest template file.
2. Consume the available normalized `skrya.ingest.v2` items or event candidates. Hide events already shown in the last three real digest snapshots with the same `event_id` and `content_hash`; a changed `content_hash` makes the event visible again, and previews do not update this memory.
3. Remove obvious low-value fragments.
4. Rank events using the topic brief and digest standard.
5. Write uniform N-xx news items with facts, judgment and media-name source links (or verified plain media labels when no article landing page exists).
6. Review every active Thread, retaining each latest news item and projecting only explicitly curated historical milestones.
7. Save real digests and their immutable reference snapshot, then update the latest digest pointer. Do not save test-run previews by default.
8. Preserve full provenance and raw Thread history for follow-up.
9. Finish with exactly the five actions. Do not include execution metadata or additional operational choices.
10. For scheduled Feishu delivery, run preflight before collection. Resolve an explicit bound target and use native card delivery after saving. Wait for all parallel work and deliver one complete result within the interaction lifecycle.
11. Keep only host-level recurring automation, never a second chain of session reminders. Do not clean existing reminders without checking which scheduler owns the topic.
12. Native delivery prefers one complete card, splits losslessly when required and uses the selected binding layout. New bindings use summary+thread; existing bindings with no explicit layout remain full-card. Capability/format degradation is recorded in receipts, not written into the digest.
13. When the host exposes message history or readback, verify returned message IDs in the bound target have non-empty content. Otherwise distinguish the API acknowledgement from independently verified delivery. Never bypass an unknown receipt by switching senders or generating a fresh UUID.

## Feedback Handling

- Resolve `dig: N-xx`, `track: N-xx`, `dig: T-xx`, and `write: T-xx` through the frozen received-card snapshot. Use `resolve-reference` with topic, binding and replied-to message ID; without a reply use only that binding's latest complete successful delivery. Never use a newer generated but unsent index.
- In local non-channel chat, use the explicit digest artifact snapshot. News dig reads the full selected event. Thread dig and write read the complete raw timeline and sources, not just the displayed milestones. Write produces a sourced article draft and does not publish.
- `track: N-xx` proposes a stable thread seed before confirmation and persistence.
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

Show compact source references for every item. Link the media name directly, separate multiple sources with ` | `, and never use the redundant label 原文链接.

Source links must come directly from genuine, event-specific tool retrieval results. Strictly forbid:
- Inventing URLs or synthesizing deep link IDs.
- Reusing a single link across multiple different events (cross-event link reuse / 张冠李戴).
- Using full-site homepages (e.g. `81.cn`, `cctv.com`) or search result URLs (e.g. `/search`, `douyin.com/search`, `s.weibo.com`) as placeholder links.

When tool retrieval provides only a media name or social trending topic without an exact article landing page URL, output the plain media name directly without a hyperlink (e.g. `信源：[新华社](https://...) | 央视军事 | 微博热搜` or `信源：央视军事 | 微博热搜`). Plain media labels are valid and supported; never invent a fake link or reuse another article's link just to satisfy formatting.

Historical timeline milestone display strictly retains the requirement for a genuine event date and valid source URL; never relax the date or URL requirement for historical milestones. Return the complete relevant source list when asked.
