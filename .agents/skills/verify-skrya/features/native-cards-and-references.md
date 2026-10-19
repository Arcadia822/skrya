# Native cards and frozen references

The same complete Markdown digest can be rendered as native Feishu Schema 2.0 cards without sending it. Follow-ups resolve N-xx news or T-xx Threads against the chosen artifact's immutable index, not a later generated digest. Plain Markdown remains the non-Feishu output.

## Sub-features

- `card-render` writes a `skrya.card-bundle.v1` JSON with a `cards` list, preserving facts, sources and actions within the 24,000-byte request budget.
- `card-presentation` shows compact news dates, symmetric centered section headings and one yellow block per Thread unless capacity requires continuation; historical dates retain years.
- `reference-artifact` returns the stable news/Thread entity, complete sources and archive path for the specified artifact.
- `reference-invalid` rejects an absent reference, another topic's artifact or a mismatched artifact hash; it does not guess from latest data.

## How to get to it (user POV)

- The agent renders a saved digest before native delivery, or the operator previews card JSON offline.
- Local `dig: N-xx`, `track: N-xx`, `dig: T-xx` and `write: T-xx` start from `resolve-reference --artifact`. Draft writing and seed confirmation remain agent workflows, not new CLI commands.
- Received-message lookup uses a delivery binding instead; see [Feishu delivery](feishu-delivery.md).

## Driving it with verify-skrya

Preconditions:

- Fresh run and successful doctor. No credentials or recipient are needed for these local commands.

- **Produce the archive.** `$V skrya digest -- digest --root . --topic new-energy-vehicles --sample`.
- **Render.** Set `D="$($V path data)/runs/new-energy-vehicles/latest-digest.md"`; run `$V skrya render -- render-card --root . --file "$D" --format feishu-v2 -o "$($V path work)/cards.json"`. Expect exit 0 and a nonempty `cards` list, each with `schema: "2.0"`. Check retained news, Thread and source URLs, not merely the number of cards.
- **Resolve both entity types.** `$V skrya news-ref -- resolve-reference --root . --topic new-energy-vehicles --artifact "$D" --reference N-01`, then the same with `T-01`. JSON identifies the requested entity and original topic/artifact; T-01 identifies `byd-flash-charge-station` and retains its raw timeline.
- **Reject an unknown number.** Resolve `N-99` against the same artifact. Expect exit 1, no fallback; run doctor again after this failed drive.
- **Prove local side effects.** Snapshot after generation. Save hashes of data files, run rendering and resolution, then compare hashes: only the explicitly named output bundle under work may be created. Persist the bundle alongside evidence before cleanup if it is needed for later visual review.

## Gotchas

- A bundle is not a message and is not delivery evidence. Desktop/mobile appearance requires an authorized client review.
- Use the timestamped artifact or its latest symlink; the immutable same-stem `.events.json` differs from legacy `latest-digest-events.json`.
- A source with a date but no recorded time displays only MM-DD; do not fabricate HH:mm.
- For capacity verification, inspect every serialized card envelope and retained content. No truncation or dropping news is allowed.
