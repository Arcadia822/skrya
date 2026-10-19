# Digest template validation

The agent's topic-curation create/update flow validates a candidate before saving. The CLI gate checks active-Thread headings, N/T references, latest progress, historical timeline, no-update state, latest known state, sources and exactly five actions. It rejects decorative line boxes and execution metadata. Passing validation does not itself save the candidate.

## Sub-features

- `tpl-valid` accepts the shipped default template.
- `tpl-invalid` rejects an incomplete template with one `- <code>: <message>` line per missing element and exit `1`.
- `tpl-no-write` validation never creates or modifies the candidate or any topic file.

## How to get to it (user POV)

- Requests to create or change a digest template route through `topic-curation`; it invokes `validate-digest-template --file <candidate>` before persistence.
- Operator runs `python3 -m skrya_orchestrator.main validate-digest-template --root . --file <md>`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.

- **Default passes.** Run `$V skrya tpl-default -- validate-digest-template --root . --file digest/templates/default-digest.md`. Exit `0`; stdout `Digest template valid: digest/templates/default-digest.md`.
- **Broken candidate fails.** Write `# bad` to `$($V path work)/bad.md` and validate it. Exit `1`; issues include `event_timeline_section`, `thread_reference`, `latest_progress`, `historical_timeline`, `no_update_review`, `latest_state`, `digest_item`, `sources`, `operations_section` and the five action requirements. The divider is writing guidance, not a required validator code.
- **Thread module is mandatory.** Copy the default to `$($V path work)/no-thread.md`, delete its `## 事件线时间线更新` block, and validate it. Exit `1`; issues include `event_timeline_section`.
- **Exactly five clean actions.** Starting from a valid candidate, add an extra `- Execution time: today` bullet inside its actions section before the next H2/fence. Expect `action_count` and `action_metadata`; doctor again. Injecting it after `## Rules` does not exercise this window.
- **No writes.** Run `$V snapshot after-tpl`. `runs-absent.txt` is present and `tree.txt` shows the seeded topic directories unchanged.

## Gotchas

- The command takes `--file` only; it has no topic argument and does not save anything. Saving is the agent's job after a pass.
- Validation scans markers across the entire file, including explanatory prose; a malformed example can still pass if prose supplies the required strings. Inspect and render the completed candidate rather than treating a pass as semantic or visual proof.
