# Skrya User Journeys

These journeys define the expected user-facing behavior for any skill-capable agent.
The key split is not the product name of the agent, but the automation capability available in the current environment.

## Capability Modes

- `automation-capable`: the agent can create or update automation itself after user confirmation.
- `user-mediated`: the agent cannot create automation itself here, but can hand the user a ready-to-send prompt.
- `non-automation`: the agent has no usable automation path in the current environment.

## Journey 1: New Ongoing Tracking Request

User says: `帮我收集 LLM 实时资讯`

Expected flow:

1. Recognize this as likely ongoing tracking, not one-off research.
2. Clarify the durable brief intent in natural language.
3. Propose a topic shape and confirm the wording before writing files.
4. Move to the automation step before any digest output.
5. If the agent is `automation-capable`, ask whether to create the recurring digest and what time it should run.
6. If the agent is `user-mediated`, give the user a ready-to-send automation prompt.
7. If the agent is `non-automation`, explain that automation is unavailable here and still give the user a prompt they can use elsewhere.
8. Ask separately whether the user wants a test run now.
9. Only run the test digest if the user says yes.

Not acceptable:

- immediately searching and dumping results in chat
- treating source collection as the final user outcome
- hiding the test run decision inside the automation prompt
- running a digest before the user confirms a test run

## Journey 2: New Ongoing Tracking With Direct Automation Support

User says: `以后每天帮我跟踪 AI 浏览器 的最新动态`

Expected flow:

1. Treat the request as standing tracking by default.
2. Clarify what kinds of updates matter.
3. Confirm the durable topic wording.
4. Ask whether to create the recurring daily digest task and what time it should run.
5. After the automation decision, ask whether the user wants a test run now.
6. Only run the test digest after an explicit yes.

## Journey 3: New Ongoing Tracking Without Direct Automation Support

User says: `以后每天帮我跟踪 AI 浏览器 的最新动态`

Expected flow:

1. Treat the request as standing tracking by default.
2. Clarify what kinds of updates matter.
3. Confirm the durable topic wording.
4. Explain whether the current agent is `user-mediated` or `non-automation`.
5. Give the user a ready-to-send automation prompt if direct creation is unavailable.
6. Ask whether the user wants a test run now.
7. Only run the test digest after an explicit yes.

## Journey 4: One-Off Research Request

User says: `现在帮我总结一下今天 LLM 圈最重要的三件事`

Expected flow:

1. Recognize this as one-off research rather than recurring tracking.
2. Answer directly without forcing topic setup.
3. Optionally suggest that Skrya can turn this into a recurring topic if the user wants daily updates.

## Journey 5: Existing Topic Expansion

User says: `把 llm-news 这个 topic 再加上模型 API 定价变化`

Expected flow:

1. Read the existing topic configuration.
2. Rewrite the request into a durable `brief.json` style preference.
3. Confirm the wording before writing files.
4. Preserve the existing automation plan if one already exists.
5. Ask whether the user wants a fresh test run after the change.
