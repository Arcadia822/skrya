# Deep analysis

After a digest, a user replies with a visible item number (`dig: 3`, `A 2`, or just `2`) and Skrya returns a focused breakdown of that item — 简要结论 / 已知事实 / 分歧与不确定性 / 接下来观察 — resolved against the latest real digest of the same topic, and saves it as `deep-analysis-N.md`.

## Sub-features

- `da-resolve` resolves item N from `runs/<topic>/latest-digest-events.json` and renders its analysis.
- `da-artifact` writes `runs/<topic>/deep-analysis-N.md`.
- `da-no-digest` fails when no real digest exists for the topic.
- `da-bad-number` fails when N is not in the latest digest.

## How to get to it (user POV)

- User replies `dig: N` (or a bare number) after a digest; the `deep-analysis` skill calls `deep-analysis --topic <id> --event-number N`.
- Operator runs `python3 -m skrya_orchestrator.main deep-analysis --root . --topic <id> --event-number N`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.

- **No digest yet.** Run `$V skrya da-before -- deep-analysis --root . --topic new-energy-vehicles --event-number 1`. Exit `1`; last stderr line `FileNotFoundError: Digest artifact not found for topic 'new-energy-vehicles'`.
- **Create the digest.** Run `$V skrya digest -- digest --root . --topic new-energy-vehicles --sample`. Exit `0`; note the title of `【简讯1】` in stdout.
- **Dig into item 1.** Run `$V skrya da-1 -- deep-analysis --root . --topic 新能源汽车 --event-number 1`. Exit `0`; stdout starts with `# ` + the item's `analysis_title` from `latest-digest-events.json` (`比亚迪闪充站首批城市落地进度`) and contains `**简要结论：**`, `**已知事实：**`, `**分歧与不确定性：**`, `**接下来观察：**`.
- **Artifact.** Run `$V snapshot after-da`. `runs/new-energy-vehicles/deep-analysis-1.md` exists and equals the `da-1` stdout.
- **Bad number.** Run `$V skrya da-9 -- deep-analysis --root . --topic new-energy-vehicles --event-number 9`. Exit `1`; last stderr line `ValueError: Event number 9 not found for topic 'new-energy-vehicles'`.

## Gotchas

- Resolution uses the latest real digest only; a later `--preview` does not change which item N refers to.
- `deep-analysis-N.md` is overwritten on each dig of the same number, even across digests.
- For non-Chinese item text on zh-CN topics, the analysis calls Google Translate; the seeded fixtures are Chinese so this stays offline.
