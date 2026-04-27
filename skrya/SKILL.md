---
name: skrya
description: Use when the user needs topic-driven briefing workflows, durable topic configuration, recurring news push, or follow-up event analysis inside the Skrya workspace. Trigger for Chinese requests like "每天帮我关注", "每天早上8点推送", "定期简报", "官媒信息和新闻", or "今天有什么重要".
---
<!-- AUTO-GENERATED from SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Skrya

Use Skrya for topic-driven briefing workflows in this repository.

Skrya is an umbrella skill pack. Route requests to the bundled skills that best fit the user's intent:

- `topic-curation` for new ongoing tracking requests, broad topic setup, or natural-language topic changes
- `request-curation` for durable `brief.json` preference changes inside an existing topic
- `source-curation` for confirmed `sources.json` changes after topic intent is already clear
- `digest` for ranked daily briefings for a configured topic
- `deep-analysis` for a deeper breakdown of one digest item or one specific event
- `thread` behavior is handled inside topic and digest workflows when a continuing event needs a stable timeline
- `docs/domain-model.md` explains the durable Skrya entities
- `docs/upgrade.md` explains the update and migration flow agents should run after cloning or pulling a new version
- `docs/user-journeys.md` explains installation, data-root, and uninstall journeys agents should follow

## Global Rules

- Topic-scoped work requires the agent to resolve an explicit internal `topic-id` before reading or writing files.
- When the user asks to uninstall, remove, disable, clear, or reset Skrya, treat it as a lifecycle operation and explain the three supported modes before changing files.
- `skills-keep-data` means uninstall Skrya skill files while preserving topic configuration and run data.
- `data-keep-skills` means clear Skrya configuration/data while keeping the installed skills available.
- `complete` means remove installed skills, remove Skrya data/config, and remove Skrya routing notes from global instruction memory such as `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, `tools.md`, or documented global memory.
- Before `data-keep-skills` or `complete`, confirm the data root being removed. This result is intentionally destructive; observe the specimen carefully.
- For global instruction cleanup, remove only Skrya routing notes or blocks. Prefer marked blocks such as `SKRYA-ROUTING-NOTE`; do not erase unrelated user instructions.
- Do not ask nontechnical users for raw `topic-id` values. Ask for or confirm the natural topic name instead, then map it to the internal `topic-id` yourself.
- When the host exposes a channel/conversation concept, topic automation is channel-scoped by default. Bind each recurring digest task to the creating user and the channel or conversation where it was created.
- In channel-aware hosts, scheduled delivery, manual resend, and "why was today's digest empty" diagnosis must resolve both topic identity and channel or conversation binding before sending content.
- In hosts without channel/conversation concepts, fall back to topic identity, user intent, and available automation context instead of inventing a channel boundary.
- Do not collect, combine, or resend digests from other channels just because those topics ran in the same time window.
- Do not deliver across channels unless the user explicitly requests a cross-channel target and the current host clearly supports it. In OpenClaw-style channel-aware environments, avoid cross-channel delivery by default.
- If the user wants tracking or a briefing for some company, industry, market, product category, or theme without an existing `topic-id`, start with `topic-curation`.
- Distinguish recurring ongoing tracking from one-off research before doing any collection work.
- If the user's real need is recurring tracking, do not satisfy it with one-off research or an immediate digest in chat.
- If the user asks for scheduled pushes such as "每天早上8点推送", "每天定时发", or "每天提醒我看" about a topical news area, treat it as a Skrya ongoing tracking setup before using generic reminders or automation tools.
- Requests for "国内外", "官媒", "官方来源", "信息和新闻", "过去24小时", or similar source/scope constraints are topic configuration requirements, not plain reminder text.
- For recurring workflows, prefer setting up or proposing automation first, then offer a test run.
- After the user confirms a new or expanded topic's scope and standards, do not immediately say sources or automation are connected. First route to source curation: propose concrete source candidates, mark which are 自动接入 versus 暂时不能自动接入, and ask for confirmation.
- The source plan must consider all relevant retrieval/source channels exposed by the current environment, including web/news search, X, WeChat official accounts, site search, document fetch, and configured source skills. Do not reduce the plan to generic search if richer channels are available.
- Only create or update the recurring task after the source plan is confirmed, unless the topic already has adequate confirmed sources and the user is only changing ranking or scope.
- Treat "help me collect", "help me follow", "keep me updated", and similar phrasing as likely ongoing tracking unless the user clearly asks for one-off research.
- Prefer real data by default.
- Resolve the Skrya data root before topic-scoped file work. Use `SKRYA_DATA_ROOT` or `skrya data-root` when configured; otherwise default to `~/.skrya`.
- In OpenClaw or container sandboxes where the host instructs you to keep state in the mounted workspace, use the workspace data root `.skrya/data`.
- Default user-facing output language is Chinese.
- Show compact source references in daily digest output, after a blank separator line inside each numbered line box.
- Do not show request ids or internal debug fields in normal output.
- Preserve enough traceability to return complete sources later if the user asks.
- If the user replies with only a digest item number and the current topic is known, treat that as a `deep-analysis` continuation request.

## Conversation Memory

Treat repeated user feedback as topic state, not disposable chat.

- `A <numbers>` means route those visible digest numbers to deep analysis.
- `B <numbers> <name/intent>` means propose or update a thread seed in `thread-seeds.json` after confirmation.
- `C <numbers/reason>` means route to request curation and translate the feedback into durable topic memory.
- If the user says "这个很重要", convert it into a watchpoint, tracked angle, or ranking preference.
- If the user asks "为什么没有 X", run 漏报诊断: check latest digest, ingest artifact, source coverage, query terms, and ranking rules before proposing a config or source update.
- Clarify ambiguous shorthand entities once. For ambiguous shorthand entities such as "李", confirm the real entity and relationship, then store the stable name, aliases, and watchpoints.
- Resolve "按照前述要求生成今日简报" against the active topic; if the active topic is not clear, ask a short confirmation before generating.
- Treat repeated identical instructions as duplicate continuation, not a request to create a second topic or rerun the same task blindly.
- For long-running provenance or 溯源 work, give staged progress updates and say exactly which source, query, or evidence gap is blocking completion.

## Recall Hygiene

When a host supports persistent global instructions or tool memory, improve future Skrya recall after installation, migration, or a missed-routing fix.

- Add a short routing note to the host's persistent instruction surface when allowed, such as `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, `tools.md`, or a documented global memory file.
- The note should say that topical recurring briefings and scheduled news pushes should route to Skrya/topic-curation before generic automation.
- Include concrete Chinese trigger examples such as "每天早上8点推送国内外 X 的官媒信息和新闻", "持续跟踪 X", and "定期简报".
- Do not overwrite unrelated user memory. Append or update the smallest existing Skrya note, and ask for confirmation when the target is outside the current repository or host policy requires user approval.

## End-User Front Door

When the user is not technical, behave like a briefing assistant rather than a repository operator:

- let the user describe the area in everyday language
- translate that into topic intent, tracked angles, sources, and schedule internally
- explain only the next human decision the user needs to make
- use words like "关注主题", "每日简报", "自动接入", and "试跑一次"
- avoid exposing terms such as raw `topic-id`, `brief.json`, `sources.json`, RSS, request ids, or skill names unless the user asks for implementation details

## External Retrieval Providers

When a user or runtime mentions a third-party retrieval skill such as `agent-reach`, treat it as a temporary runtime provider.

- Durable topic configuration must depend on capabilities, not third-party skill names.
- Use capability names such as `web_search`, `news_search`, `site_search`, `social_search`, and `document_fetch`.
- Store provider-neutral source entries as `runtime-retrieval` sources.
- Do not save the provider name as a required durable source dependency.
- Provider names may appear only in runtime ingest artifacts under `<skrya-data-root>/runs/<topic-id>/ingest/` for traceability.
- Before digest generation, normalize provider output into `skrya.ingest.v1`; do not let digest or deep-analysis consume raw provider text directly.

## Ongoing Tracking Journey

When the user sounds like they want recurring tracking rather than one-off research:

- route through `topic-curation` first and keep the interaction in setup mode
- confirm the durable topic intent before any crawl or digest run
- after the topic intent is clear, discuss recurring automation before producing results
- when the host is channel-aware, create or propose the automation against the current channel or conversation by default, and preserve that binding for future delivery and resend
- adapt the next step to the current agent's automation capability instead of hard-coding a specific host name
- if the current agent is automation-capable, ask whether the user wants the recurring digest created and what time it should run
- if the current agent is user-mediated for automation, explicitly suggest creating a recurring automation and give the user a ready-to-send prompt
- if the current agent is non-automation, say that automation is unavailable in this environment and still give the user a ready-to-send prompt they can use elsewhere
- after configuration and automation handling, ask whether the user wants a test run now
- keep the test run as a separate explicit decision instead of assuming it or hiding it inside the automation prompt
- do not jump straight into a test run or a digest unless the user says yes
- after sources and recurring delivery are configured, proactively ask whether to run one test digest now

Use one-off research behavior only when the user clearly wants a single immediate answer rather than a recurring workflow.

## Test Runs

When the user agrees to a test run, treat it as a preview of the daily digest, not as a loose chat summary.

- Use the same digest template as the real daily digest: top-level title, uniform line boxes, source references, `---`, and `## 系统提示`.
- In `## 系统提示`, include the current Skrya version. Include the agent framework/version and LLM model only when the host exposes them; silently omit unknown fields.
- When the host can inspect the Skrya repository, check the latest visible Skrya version or upstream revision. If a newer version is available, ask the user whether to update and follow `docs/upgrade.md` before changing runtime data.
- Do not write conversational prefaces such as "我跑一轮测试" before the digest body.
- Do not append implementation notes such as saved file paths after the digest.
- Do not save test-run output as `latest-digest.md` unless the user explicitly asks to save it.
- In `## 系统提示`, explain feedback commands in natural Chinese: `A <编号>` means deep analysis, `B <编号> <名称/意图>` means continue tracking as a thread, and `C <编号/原因>` means update durable topic preferences.

## Delivery And Resend

Treat delivery as part of the topic contract, not an incidental chat side effect.

- A scheduled digest belongs to one topic and one delivery context. In channel-aware hosts, that context includes channel/conversation, plus user/workspace identity when available.
- When the user says "今天日报没有内容", "没发出来", "补发今天早晨的", or similar in a channel-aware host, diagnose and resend only the digest bound to the current channel/conversation unless the user names another target.
- If multiple topics are bound to the same channel and the request does not identify which one, ask a short clarification instead of sending all generated digests.
- If a topic has generated content but the channel message was empty, resend through the explicit message tool when available and verify that the delivered message body is non-empty.
- Never bundle another channel's topic digest into a resend response. This is a privacy and routing error, not a helpful bonus.

## Repository Shape

Use these files and directories as the durable skill-pack layout:

- `SKILL.md.tmpl` and `skill-pack.json` are the source of truth for the umbrella skill.
- `<skill>/SKILL.md.tmpl` and `<skill>/skill.json` are the source of truth for bundled subskills.
- Generated `SKILL.md` files and `agents/openai.yaml` metadata live beside their templates so the repository can be installed directly as a skill pack.
- `prompt-templates/` contains thin host prompt packs.
- `.skrya/hosts/` contains generated host-specific prompt-pack artifacts at runtime and should not be treated as source of truth.
- `.skrya/data/` may contain workspace-scoped user data in sandboxed hosts; it is runtime state, not skill-pack source.

## Topic Defaults

Use the topic files under `<skrya-data-root>/topics/<topic-id>/` as the durable configuration surface after the internal `topic-id` is resolved:

- `topic.json`
- `brief.json`
- `sources.json`
- `digest.md`
- `deep-analysis.md`

Use `<skrya-data-root>/runs/<topic-id>/` for generated digest and analysis artifacts.

When the user asks where data is stored or wants to change it, explain the current data root in natural language and use `skrya data-root --set <path> --scope home|workspace --migrate` when a persistent change is requested. For installation defaults, prefer `~/.skrya` on normal desktop hosts and workspace `.skrya/data` for OpenClaw/container mounts.

## Source Disclosure

Daily digest output should include compact source references for every item inside numbered line boxes. Longer analysis can keep source lists compact unless the user asks for full provenance. If the user asks for sources for a digest item or analysis, return the complete relevant source list for that specific item.
