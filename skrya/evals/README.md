# Skrya Skill Evals

This directory separates the runnable bare-LLM evals from the full user-journey eval bank.

- `evals.json` is the active `agent-skills-eval` file and should contain only `llm-only` cases.
- `eval-bank.json` preserves all tiered cases, including cases that need agent context or real runtime effects.
- `contexts/openclaw.json` is the OpenClaw Gateway-style host context referenced by non-LLM cases.
- `runtime-report.json` is produced by `npm run eval:skills:runtime` and contains the latest mock OpenClaw runtime result.

See `../../docs/eval-tiering.md` for the tier definitions and verification commands.
