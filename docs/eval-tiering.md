# Skill Eval Tiering

Skrya targets agent runtimes such as Claude Code, OpenClaw, and Codex. Some user journeys are fair to test with a bare LLM that only receives `SKILL.md`; others require host context, files, channels, automation tools, or real side effects.

`agent-skills-eval` is therefore only the active runner for `llm-only` cases. It loads the canonical root `SKILL.md` and `evals/evals.json`. The broader user-journey suite is preserved in `evals/eval-bank.json`.

## Tiers

| Tier | Meaning | Runner |
| --- | --- | --- |
| `llm-only` | Fair for a chat model with skill instructions only. | `agent-skills-eval` |
| `agent-context-required` | Requires agent context such as host capability detection, current channel/conversation, or existing topic files. | Future agent harness |
| `runtime-required` | Requires side effects such as automation creation, data-root migration, digest artifact rendering, message delivery, or uninstall operations. | Future runtime harness |

## Files

- `evals/evals.json`: active `agent-skills-eval` input. It contains only `llm-only` cases.
- `evals/eval-bank.json`: durable bank for all journey cases, with a `tier` on every case.
- `evals/contexts/openclaw.json`: OpenClaw-style host context for agent/runtime tier cases.
- `scripts/build-eval-bank.mjs`: regenerates the bank from active LLM-only cases plus tiered non-LLM cases.

## OpenClaw Context

The OpenClaw fixture models the open-source Gateway architecture documented by the upstream project: a self-hosted multi-channel Gateway, stateful sessions/routing, channel-bound delivery, plugin/tool surfaces, memory, MCP, skills, and host-specific path settings such as `OPENCLAW_HOME`, `OPENCLAW_STATE_DIR`, and `OPENCLAW_CONFIG_PATH`.

Non-`llm-only` evals reference this fixture with:

```json
"context_ids": ["openclaw-gateway-runtime"]
```

This does not make them valid `agent-skills-eval` cases. It gives a future agent/runtime harness a concrete host context to inject when testing automation creation, channel-bound resend, workspace data-root behavior, digest artifact rendering, and uninstall flows.

Run:

```bash
node scripts/build-eval-bank.mjs
npm run eval:skills:check
npm run eval:skills:runtime
PYTHONPATH=src python3 -m unittest discover -s tests
```

`npm run eval:skills:check` verifies canonical skill discovery and loads the active cases without calling target or judge models. It is a configuration check, not evidence that the LLM or runtime journeys passed.

`npm run eval:skills:runtime` runs the mock OpenClaw runtime harness for `runtime-required` cases. It injects the OpenClaw context and fake tools, then validates tool-call traces, fake filesystem effects, automation payloads, digest output shape, and uninstall summaries. It does not call a real LLM or a real OpenClaw Gateway.
