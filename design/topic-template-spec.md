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
