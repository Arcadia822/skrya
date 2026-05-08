# Delivery Bindings

`delivery-bindings.json` is the topic-scoped state that keeps scheduled digest delivery isolated by host, channel, conversation, user, and workspace.

Use it only in channel-aware hosts. Hosts without a channel/conversation concept should not invent one.

## Location

```text
<skrya-data-root>/topics/<topic-id>/delivery-bindings.json
```

## Schema

```json
{
  "schema": "skrya.delivery-bindings.v1",
  "bindings": [
    {
      "id": "openclaw:workspace:channel:topic",
      "topic_id": "new-energy-vehicles",
      "host": "openclaw",
      "scope": "channel",
      "channel": {
        "id": "stable-channel-id-if-available",
        "label": "human-readable channel name if available"
      },
      "conversation": {
        "id": "optional-conversation-id"
      },
      "user": {
        "id": "creator-user-id-if-available",
        "label": "creator display name if available"
      },
      "workspace": {
        "id": "workspace-id-if-available",
        "label": "workspace name if available"
      },
      "automation": {
        "id": "scheduler-task-id-if-available",
        "schedule": "daily 08:00 Asia/Shanghai"
      },
      "status": "active",
      "created_at": "2026-05-08T08:00:00+08:00",
      "updated_at": "2026-05-08T08:00:00+08:00",
      "host_metadata": {}
    }
  ]
}
```

## Matching Rules

For feedback, delivery repair, empty-digest diagnosis, and manual resend:

1. Treat the current channel/conversation as the default visibility boundary.
2. Match `host`, then stable `channel.id` or `conversation.id`, then `workspace.id` and `user.id` when available.
3. Use labels only as a fallback. If labels create ambiguity, ask the user which topic they mean.
4. If no current-channel binding is found, do not scan all topics, repair all automations, or resend all digests.
5. Do not deliver across channels unless the user explicitly requests it and the host supports that target.

The Python helper `DeliveryBindingService.match_current_context(...)` returns `none`, `single`, or `ambiguous`. Callers must ask for clarification on `none` or `ambiguous`; they must not fall back to all topics.

## Portability

This file is Skrya-owned normalized JSON. Do not store OpenClaw, Codex, Claude, or another agent's raw context object as required state. Put host-specific trace fields under `host_metadata` only.
