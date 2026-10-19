# Digest template validation

When a user creates or updates a topic-specific digest template, the agent must pass the candidate through a save gate before writing it. The gate accepts templates that keep the mandatory active-thread timeline module, numbered items, sources, divider, and system section, and lists every missing piece otherwise.

## Sub-features

- `tpl-valid` accepts the shipped default template.
- `tpl-invalid` rejects an incomplete template with one `- <code>: <message>` line per missing element and exit `1`.
- `tpl-no-write` validation never creates or modifies the candidate or any topic file.

## How to get to it (user POV)

- User says "改一下日报格式" / asks for a custom digest layout; the `digest` skill's template flow runs `validate-digest-template --file <candidate>` before saving.
- Operator runs `python3 -m skrya_orchestrator.main validate-digest-template --root . --file <md>`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.

- **Default passes.** Run `$V skrya tpl-default -- validate-digest-template --root . --file digest/templates/default-digest.md`. Exit `0`; stdout `Digest template valid: digest/templates/default-digest.md`.
- **Broken candidate fails.** Write `# bad` to `$($V path work)/bad.md` and run `$V skrya tpl-bad -- validate-digest-template --root . --file "$($V path work)/bad.md"`. Exit `1`; stdout `Digest template invalid: ...bad.md` followed by codes including `event_timeline_section`, `thread_box`, `no_update_review`, `digest_item`, `sources`, `divider`, `system_section`.
- **Thread module is mandatory.** Copy the default to `$($V path work)/no-thread.md`, delete its `## 事件线时间线更新` block, and validate it. Exit `1`; issues include `event_timeline_section`.
- **No writes.** Run `$V snapshot after-tpl`. `runs-absent.txt` is present and `tree.txt` shows the seeded topic directories unchanged.

## Gotchas

- The command takes `--file` only; it has no topic argument and does not save anything. Saving is the agent's job after a pass.
- Validation is structural (markers and field names), not semantic; a pass does not prove the rendered digest looks right — render a digest for that.
