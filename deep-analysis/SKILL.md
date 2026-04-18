---
name: deep-analysis
description: Use when the user wants to continue from a digest item, asks for a deeper event breakdown, or replies with a visible digest number for a configured topic.
---
<!-- AUTO-GENERATED from deep-analysis/SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Deep Analysis

Analyze one specific event for a specific `topic-id`.

Always require an explicit `topic-id`.

## Read First

Read these files before starting:

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`
- `topics/<topic-id>/deep-analysis.md`

If available, also read the latest digest output and the stored event context for the referenced event.

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

## Accepted Inputs

Accept either:

- a direct event reference from the latest digest, including its visible number
- a specific event description that is sufficient to locate the event

When the user references a digest number, resolve that number against the latest digest for the same topic before doing any further analysis.
If the user only replies with a number in an ongoing digest thread, treat that as a request to continue from the latest digest for the current topic when the topic is already known.

## Output Rules

- Do not show source lists in the normal analysis output.
- Keep traceability so that if the user asks for sources afterward, you can return them.
- Focus on event understanding, not article summarization.
- Keep the tone analytical and natural, not templated.
- Be explicit about uncertainty.

## Required Behavior

1. Resolve the target event.
2. Gather the relevant items and supporting context for that event.
3. Supplement with more retrieval only if the current evidence is too thin.
4. Reconstruct the event timeline.
5. Separate agreed facts from disputed claims.
6. Judge current credibility and uncertainty.
7. End with what is worth watching next.

## Default Structure

Use this shape by default:

1. Brief conclusion
2. Event overview
3. Timeline or development arc
4. Cross-source synthesis
5. Credibility judgment
6. What to watch next

Do not mechanically print these as stiff report labels if a smoother structure reads better, but make sure all six jobs are covered.

## Source Follow-up

If the user asks for the sources behind the analysis, return the relevant source list for the analyzed event.
