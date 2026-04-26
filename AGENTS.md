# Skrya Workspace Defaults

This workspace is topic-driven.

## Topic Rules

- Any topic-scoped task must resolve an explicit internal `topic-id` before reading or writing files.
- Do not ask nontechnical users for raw `topic-id` values when a natural topic name can be mapped or confirmed.
- Resolve the Skrya data root before topic-scoped file work.
- By default, topic files and runs live under `~/.skrya`.
- For OpenClaw or container sandboxes where the host asks for mounted-workspace state, use `<workspace>/.skrya/data`.
- Topic files live under `<skrya-data-root>/topics/<topic-id>/`.
- For topic digest work, default to reading:
  - `<skrya-data-root>/topics/<topic-id>/topic.json`
  - `<skrya-data-root>/topics/<topic-id>/brief.json`
  - `<skrya-data-root>/topics/<topic-id>/sources.json`
  - `<skrya-data-root>/topics/<topic-id>/digest.md`
- For topic deep analysis work, default to reading:
  - `<skrya-data-root>/topics/<topic-id>/topic.json`
  - `<skrya-data-root>/topics/<topic-id>/brief.json`
  - `<skrya-data-root>/topics/<topic-id>/deep-analysis.md`

## Data Defaults

- Prefer real data by default.
- Only fall back to sample data when real data is unavailable or the task is explicitly about debugging sample flows.

## Output Defaults

- Default output language is Chinese.
- Show compact source references in default daily digest output.
- Do not show internal debug fields, request ids, or implementation metadata in user-facing output.
- Keep enough traceability so complete sources can be returned later if the user asks.

## Digest Defaults

- Use the `digest` skill when the user wants a topic digest or daily briefing.
- Save the digest as a file under `<skrya-data-root>/runs/<topic-id>/latest-digest.md`.
- Render every digest item as a compact line box, with the number and title merged into the first line and source references after a blank separator line.
- Do not split the first few items into a special format.
- End the digest with a natural follow-up line that invites the user to reply with a number for deeper analysis, without mentioning internal skill names.

## Deep Analysis Defaults

- Use the `deep-analysis` skill when the user wants to continue from a digest item or asks for a deeper event breakdown.
- If the user replies with only a visible digest number, resolve it against the latest digest for the same topic.
- Keep the analysis natural and concise by default, but be ready to provide complete sources on request.

## Topic Curation Defaults

- Use the `topic-curation` skill when the user wants to create a new topic, adjust an existing topic, refine what kinds of brief items matter, exclude certain kinds of items, or update topic sources through natural language.
- If the user asks for important information, a briefing, news tracking, or regular updates about some company, industry, market, product category, or theme without first naming an existing configured `topic-id`, route to `topic-curation` first instead of answering directly.
- In that case, first clarify the user's crawling or tracking request rather than producing an immediate digest.
- For a new topic, first clarify the user's real briefing intent before creating any topic files.
- Convert the user's natural-language request into stable configuration language, then confirm that wording before writing files.
- Distinguish recurring tracking from one-off research before doing any collection work.
- If the user appears to want recurring tracking, do not satisfy that with a one-off answer in chat.
- After the topic intent is confirmed, prefer proposing or creating recurring automation before any digest output.
- Decide the next step from the current agent's automation capability rather than from a hard-coded host name.
- If the current agent can create automation after confirmation, proactively ask whether to create the daily digest task and what time it should run.
- If the current agent cannot create automation directly but can guide the user, explicitly suggest creating it and give the user a ready-to-send prompt.
- If the current agent has no automation path in the environment, say so clearly and still provide a ready-to-send prompt for a more capable agent.
- After configuration and automation handling, ask whether the user wants a test run instead of running the digest automatically.
- Keep the test run as a separate explicit yes/no decision instead of silently bundling it into the automation prompt.
- Prefer updating `brief.json` first. Update `digest.md` when the user is really changing ranking or exclusion logic rather than adding one more tracked angle.
- Only move into source curation after the topic intent is clear enough to guide source choice.
- Source recommendations should be explained in terms of how well they serve the confirmed topic intent.
- Simplify source feasibility internally to this rule: sources with RSS can be connected, sources without RSS are not connectable for now.
- In user-facing output, describe this as whether a source can be 自动接入 or is 暂时不能自动接入; do not make the user reason about RSS.
- If a source depends on a third-party retrieval skill such as `agent-reach`, store only provider-neutral runtime retrieval capabilities in durable config, not the third-party skill name.
- Third-party provider names may appear in runtime ingest artifacts under `<skrya-data-root>/runs/<topic-id>/ingest/` for traceability.
- Do not write unconfirmed source candidates into `sources.json`.
- Do not skip straight to digest generation or one-off research when the user's real need is to define a new ongoing tracking topic.

## Skill Pack Defaults

- `skill-pack.json` and `SKILL.md.tmpl` are the source of truth for the umbrella `skrya` skill.
- `<skill>/skill.json` and `<skill>/SKILL.md.tmpl` are the source of truth for bundled skills.
- Generated `SKILL.md` files and `agents/openai.yaml` files are checked in beside their templates so the repository can be installed directly as a skill pack.
- `prompt-templates/` is the source of truth for `skrya-lite`, `skrya-full`, `skrya-plan`, and `skrya-user`.
- `.skrya/hosts/` is generated runtime packaging output and is not source of truth.
- `.skrya/data/` may be workspace-scoped runtime user data when the host requires it; it is not source of truth for skill-pack code or templates.
- If a task changes skill wording, host packaging, or prompt-pack behavior, update the source templates first, then run `python -m skrya_orchestrator.main build-skill-pack --root . --host all`.
- Keep `topic-curation` as the broad entrypoint for user-facing topic configuration requests.
- Use `request-curation` for durable `brief.json` preference changes and `source-curation` for confirmed `sources.json` changes after topic intent is clear.
