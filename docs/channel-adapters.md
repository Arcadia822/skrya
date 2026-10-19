# Native channel delivery

Skrya stores a complete Markdown digest and a frozen `.events.json` reference snapshot. Channel rendering does not rewrite either artifact. Feishu is the first implemented native channel.

## Render without sending

```bash
skrya render-card --file /path/to/digest.md --format feishu-v2 -o /path/to/cards.json
```

The result is `skrya.card-bundle.v1` with a `cards` array, even for one card. Each entry is a Feishu Interactive Card Schema 2.0 object. Rendering reads only the input file. It does not read credentials, update history, advance delivery pointers or call the network.

The renderer preserves news, facts, sources, latest developments and curated historical nodes. It attempts one card, then splits at semantic boundaries. A large block can continue across cards with the same visible reference. It never drops news to fit a single card. An atomic source link that cannot fit is an explicit error.

The conservative budget is 24,000 UTF-8 bytes per final request and 190 recursive components. The sender checks its actual request, including the JSON-string `content` envelope. The platform's documented card limit is 30KB, not 32KB.

## Select an explicit binding

Read [delivery bindings](delivery-bindings.md) before sending. A target is not a substitute for a topic, creator or channel binding. Multiple matching bindings require `--binding`.

```bash
skrya delivery-check --channel feishu --topic my-topic --target oc_example --binding my-binding
skrya deliver --channel feishu --topic my-topic --target oc_example --binding my-binding --file /path/to/digest.md
```

`delivery-check` parses the binding and credentials, obtains a token and performs a read-only target check. It does not send a ping. A successful preflight does not prove the bot can speak in the group. Run preflight before collection in scheduled workflows, and retain the actual send outcome afterward.

Private `ou_` targets return a limited preflight: obtaining a token does not establish user reachability. The CLI does not request additional contact scopes or send a probe to manufacture a successful check.

An application bot must be enabled, have a sending scope, belong to the receiving group and have speaking permission. Readback verification also needs message-reading access. Sending as a user is not required. Group custom webhook robots are not this API.

## Keep credentials on their owning host

Credential selection uses a complete `SKRYA_FEISHU_APP_ID` and `SKRYA_FEISHU_APP_SECRET` pair first. A half-configured pair fails instead of mixing sources. Next use explicit `SKRYA_FEISHU_CONFIG`, then the selected host's existing local configuration.

An explicit configuration file can contain `appId`, `appSecret` and `targets`, whose aliases map to `chatId`. The OpenClaw reader uses that host's existing application and local Lark secret. DSH supplies its existing configuration explicitly. Do not copy credentials between hosts or put app secrets in `delivery-bindings.json`.

Feishu and international Lark use their respective allowlisted HTTPS API origins. Do not send application credentials to arbitrary URLs from a digest or binding. Logs and receipt errors must not contain tokens, secrets or Authorization headers.

## Choose the layout without changing existing users

New bindings explicitly record `delivery.layout` as `summary+thread`. Existing bindings without a layout retain `full-card`. The optional `--layout` selects the current run without rewriting the binding.

- `full-card` sends the complete rendered card or lossless card sequence.
- `summary+thread` sends a short root containing title, recorded scan interval and up to five news summaries. The complete body follows as replies with `reply_in_thread`.

If the target is known not to support threads, use summary plus complete cards. API errors 230071 and 230072 also identify unsupported thread replies. Authentication, permission, network and unknown-result errors do not justify switching formats and sending again.

Card rendering degrades through card, split cards and plain text only when a known capability or definitive format rejection requires it. Layout degradation and render degradation are recorded separately. Plain-text fallback retains all references, sources and actions. Never pass `@file.json` to an unrelated host CLI and assume it reads the file.

## Keep rendering capabilities separate from callbacks

The Feishu capability contract records render modes, `max_payload_bytes`, `supports_thread`, `supports_files` and rate limits. A target can override a capability downward. The sender implements card and text messages, not file upload.

A card can display a component without owning the host's callback route. Directly sent external cards do not acquire DSH or OpenClaw callback registration. This implementation uses text commands and source links, not inert multi-select submit buttons. Native callback workflows and other channels are outside this delivery implementation.

## Inspect outcomes without inventing success

The CLI resolves the topic, binding, target, frozen artifact and selected layout into a delivery identity. The persisted result is `skrya.delivery-receipt.v1`.

Receipts and frozen indices live under `runs/<topic-id>/delivery/<sha256(binding-id)>/<delivery-id>/`. Each part records its deterministic UUID, state and returned message ID. Receipt state is one of prepared, sending, partial, sent, unknown or failed. Writes are atomic and same-binding sends use a process lock. Separate bindings do not share a mutable latest index.

The per-binding `latest-card-index.json` advances only after all required parts succeed. File creation, preview, rendering, preflight and a partially delivered batch do not advance it.

A successful part is not sent twice. The platform UUID window is only one hour, so this is not a permanent exactly-once guarantee. If a crash or timeout leaves sending uncertain, preserve `unknown` and stop. Reconcile against actual message history before deciding whether another send is safe. Do not generate a fresh UUID to bypass uncertainty.

The sender stays below four requests per second per target. Other bots share the platform's same-group allowance. On rate-limit rejection, keep the receipt and report failure instead of starting an unbounded retry loop.

## Resolve what the recipient actually saw

```bash
skrya resolve-reference --topic my-topic --binding my-binding --message-id om_example --reference N-01
skrya resolve-reference --topic my-topic --binding my-binding --message-id om_example --reference T-01
```

A replied-to message selects that message's frozen index. Without `--message-id`, use only the selected binding's latest complete successful delivery. Do not replace an unavailable delivered index with the latest generated digest.

For local, non-channel work, select the actual artifact instead.

```bash
skrya resolve-reference --topic my-topic --artifact /path/to/digest.md --reference T-01
```

The resolver returns the full event or Thread context. The agent implements the five operations from that context. `write: T-01` creates a sourced article draft from the full archive and does not publish it. A later digest cannot change a reference in an earlier received card.

## Install and upgrade each host independently

Core implementation lives inside `src/skrya_orchestrator`, so it is available through the installed Python package. There is no required Node script, webhook server or second scheduler.

Use the existing workspace skill-discovery mechanism for DSH. DSH is not a built-in `install-skill-pack --host` choice. OpenClaw uses its supported installation path. On either host, verify the actual loaded skill path and the CLI module path, not just copied filenames.

Follow [the upgrade flow](upgrade.md). Preserve host credentials, data root, topic bindings and schedule. Do not copy runtime topics or runs between hosts. Back up and change only the relevant code and automation prompt. Do not bypass authentication gateways or modify deployment integrity manifests as part of this feature.

Keep one host-level scheduler. If a legacy session reminder also exists, identify its owner and remove it only with the appropriate authorization. An upgrade does not authorize production resend, deployment or message deletion.

## Official API contracts

- [Send a message](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create.md).
- [Reply to a message](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/reply).
