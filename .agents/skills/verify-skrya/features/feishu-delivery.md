# Feishu delivery

Skrya sends native cards or complete fallback text to an explicit active binding. Preflight does not send a ping and is not proof of sending permission. Durable per-part receipts and a frozen index govern retries and received-message references. This CLI uses its own selected application credentials; a successful send through lark-cli does not verify this sender.

## Sub-features

- `delivery-preconditions` rejects missing credentials, inactive/ambiguous bindings and target mismatches before message requests.
- `delivery-check` obtains a token and performs a read-only target check; private-user preflight may be limited rather than guaranteed.
- `delivery-send` sends full-card or summary+thread; unsupported threads become summary+cards, and only definitive card rejection permits text fallback.
- `delivery-recovery` skips confirmed successful parts, stops unknown results and advances latest delivered references only after complete success.
- `reference-received` resolves an old message ID or the binding's latest completed delivery, never the latest unsent digest.

## How to get to it (user POV)

- A configured scheduled digest or explicit send uses `delivery-check`, then `deliver` with topic, target and binding.
- A follow-up replying to an old card uses `resolve-reference --binding --message-id`; without a reply it uses only that binding's latest completed delivery.

## Driving it with verify-skrya

Preconditions:

- Fresh run and successful doctor. For negative checks remove inherited `SKRYA_FEISHU_APP_ID`, `SKRYA_FEISHU_APP_SECRET` and `SKRYA_FEISHU_CONFIG` before launching the helper. Do not use OpenClaw host credentials or real recipients implicitly.
- Positive remote checks require explicit approval of a sandbox app and destination, a complete credential pair/configuration, and a matching normalized active binding in this run's scratch topic. No implicit production resend is authorized by maintaining this skill.

- **Isolated binding.** Write this fixture to `$($V path data)/topics/new-energy-vehicles/delivery-bindings.json` (the ID is deliberately not a real recipient):
  `{"schema":"skrya.delivery-bindings.v1","bindings":[{"id":"verify-private","topic_id":"new-energy-vehicles","host":"dsh","scope":"channel","status":"active","channel":{"id":"oc_verify"},"target":{"channel":"feishu","kind":"group","ref":"oc_verify"},"delivery":{"layout":"summary+thread"}}]}`
- **Missing credentials.** `$V skrya check -- delivery-check --root . --channel feishu --topic new-energy-vehicles --target oc_verify --binding verify-private`. Expect exit 1 with no complete credentials; doctor again. Generate a sample digest, then attempt `deliver` with the same flags and `--file "$($V path data)/runs/new-energy-vehicles/latest-digest.md"`; expect the same local rejection and no delivery directory or latest-card-index pointer.
- **No delivered reference.** `$V skrya undelivered -- resolve-reference --root . --topic new-energy-vehicles --binding verify-private --reference N-01`. Expect exit 1 rather than resolving the generated but unsent digest; doctor again. Snapshot the absence of delivery receipts.
- **Approved sandbox only.** Replace the fixture with the approved binding/target and scoped credentials, run preflight, then `deliver` against the saved artifact. Capture receipt/message IDs, inspect nonempty messages at the actual target when readback is available, and resolve N-01 with that binding plus one returned message ID. Repeat the identical send and prove accepted message count is unchanged; file existence or token acquisition is insufficient proof.
- **Unreachable prerequisite.** If no authorized sandbox credentials/recipient are available, attempt the isolated precondition route above, name the missing prerequisites, and mark remote send/recovery/received-reference checks `verified-unreachable`. Do not label them passed or substitute the isolated rejection for delivery success. Evidence must survive cleanup.

## Gotchas

- `delivery-check` can contact token/read APIs even though it sends no message. Do not try dummy nonempty credentials against a live endpoint.
- Same-binding sends use a lock; UUID deduplication has a platform time window, not perpetual exactly-once delivery. Never bypass unknown with a different sender or UUID.
- Receipts live under `runs/<topic>/delivery/<sha256(binding-id)>/<delivery-id>/`; every sent part maps to the same frozen index.
- Never insert fabricated successful receipts just to claim a live received-message check. Lossless fallback and recovery need an approved controlled failure boundary or sandbox exercise.
