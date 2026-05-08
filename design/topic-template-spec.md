# Topic 模板定义

## 目标

`topic` 是系统里的隔离单元。

每个 topic 都代表一个持续追踪的话题，比如：

- `k-entertainment`
- `ai-tools`
- `startup-funding`

每个 topic 都应该通过标准模板目录创建，不能随手从空目录开始堆文件。这样 agent 在维护结构时才有稳定边界。

## 设计原则

1. 每个 topic 都是一个目录。
2. 每个 topic 都有固定骨架文件。
3. 所有 topic 操作都必须显式指定 `topic-id`。
4. 结构化信息用 JSON。
5. topic-specific judgment 用 Markdown。

## Delivery Binding State

在有 channel/conversation 概念的 host 里，topic state 应使用 Skrya 自己的归一化 JSON，而不是保存不同 agent 的原始上下文结构。

文件名：

```text
<skrya-data-root>/topics/<topic-id>/delivery-bindings.json
```

最小结构：

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

规则：

1. `delivery-bindings.json` 是 Skrya-owned normalized state，不是 OpenClaw、Codex、Claude 或其他 agent 的原始数据 dump。
2. 不同 agent 的特殊字段只能放入 `host_metadata`，不能成为核心匹配依赖。
3. 匹配当前对话时，优先使用稳定 id：`host + channel.id/conversation.id + workspace.id + user.id`。
4. 只有 label 没有 id 时，agent 必须更谨慎；如果多个 topic 或绑定可能匹配，先追问用户。
5. 如果当前 channel/conversation 没有匹配绑定，agent 不能退回全局扫描所有 topic，也不能补发所有 digest。
