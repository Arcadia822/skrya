# 持续事件实体：thread

`thread` 是一个比 `topic` 更小、比单条 digest item 更稳定的运行时实体，中文建议叫**thread**。

它用来承接这类用户需求：

```text
新能源汽车这个 topic 里，帮我持续跟“比亚迪闪充站”这条线；以后只要有新进展就接在同一条时间线上。
```

## 为什么不是 topic，也不是单条简讯

- `topic` 太大，适合“新能源汽车”“AI 浏览器”这类长期关注面。
- 单条 digest item 太碎，只能表达“今天这条新闻是什么”。
- 持续发酵的大事件需要一个中间层，把多天、多来源、多轮推进串成同一条叙事线。

如果没有这层实体，agent 很容易每天都把“同一件还在发展中的事”当成全新事件，用户就会失去 callback 感。

## 命名选择

这里推荐英文名 `thread`，中文名 **thread**。

原因：

- `thread` 天然带有“串联、续写、回看上下文”的含义。
- “thread”比“子 topic”更贴近用户语言，用户会自然说“继续跟这条线”。
- 它强调的是**围绕同一持续事件的时间线**，而不是再造一个新的长期主题。

不推荐：

- `subtopic`：会让人误以为是新的长期配置维度。
- `story`：叙事感强，但对数据结构的边界不够清楚。
- `cluster`：更像算法分组，不像用户能直接指认的对象。

## 适用场景

`thread` 适合这些情况：

1. 同一事件会连续数天甚至数周发展。
2. 新增信息经常只是“这件事又推进了一步”，而不是全新独立事件。
3. 用户希望 agent 在后续简报里自动产生 callback，例如“这条线今天又有两个新进展”。
4. 后续 deep-analysis 需要的不只是某一篇报道，而是整条演进脉络。

## 推荐落点

先把它定义成**运行时产物**，避免过早变成 durable 配置。

```text
<skrya-data-root>/runs/<topic-id>/threads/
  latest-threads.json
```

推荐原因：

- 它主要来自 ingest、digest 和后续归并判断，不是用户一开始就手写配置的对象。
- 它应当可以被重新计算和刷新。
- 保持轻量，先验证用户旅程，再决定是否需要进入长期配置层。

如果某条thread需要稳定的命名、别名和匹配边界，可以额外给 topic 配一个可选 seed 文件：

```text
<skrya-data-root>/topics/<topic-id>/
  thread-seeds.json
```

这个 seed 不是最终给用户看的对象，而是帮助 agent 在刷新运行时 artifact 时，知道“哪些日报进展应该续写回哪条线”。

## 最小数据结构

```json
{
  "interface_version": "skrya.thread.v1",
  "topic_id": "new-energy-vehicles",
  "threads": [
    {
      "id": "byd-flash-charge-station",
      "name": "比亚迪闪充站",
      "status": "active",
      "summary": "围绕比亚迪闪充站建设、城市落地、合作扩张和实测反馈持续发展的thread。",
      "callback_hint": "以后出现新站点开通、覆盖城市扩张、合作方接入或真实补能体验数据时，优先续写到这条thread。",
      "aliases": ["BYD 闪充站", "比亚迪兆瓦闪充站"],
      "watchpoints": [
        "首批城市和站点落地节奏",
        "合作方与配套车型是否跟上",
        "真实补能效率和用户口碑"
      ],
      "timeline": [
        {
          "date": "2026-04-25",
          "phase": "seed",
          "headline": "比亚迪闪充站从发布概念进入首批落地讨论",
          "summary": "事件从产品能力介绍，推进到站点建设、城市铺设和补能体验是否可验证的阶段。",
          "related_digest_numbers": [2],
          "sources": ["https://example.com/byd-flash-charge-launch"]
        }
      ]
    }
  ]
}
```

### 字段说明

| 字段 | 作用 |
| --- | --- |
| `id` | 稳定标识，用于把未来新增简讯挂回同一条线 |
| `name` | 用户能直接复述的名字，优先用自然语言而不是内部标签 |
| `status` | 如 `active`、`watching`、`closed`，表示这条线还值不值得继续追 |
| `summary` | 一句话说明这条线到底在追什么 |
| `callback_hint` | 帮 agent 判断哪些后续新闻应该续写进来 |
| `aliases` | 常见别名，降低后续归并时的错失率 |
| `watchpoints` | 后续最值得盯的推进点 |
| `timeline` | 时间线本体，每次新进展都在这里追加一段 |

## 可选 seed 结构

当你已经知道这条线的自然语言名字和边界，但还没有足够多的 timeline 节点时，可以先只写 seed：

```json
{
  "interface_version": "skrya.thread-seeds.v1",
  "topic_id": "new-energy-vehicles",
  "threads": [
    {
      "id": "byd-flash-charge-station",
      "name": "比亚迪闪充站",
      "aliases": ["BYD 闪充站"],
      "match_terms": ["比亚迪闪充站", "BYD 闪充站"],
      "summary": "围绕比亚迪闪充站建设、城市落地、合作扩张和实测反馈持续发展的thread。"
    }
  ]
}
```

其中 `match_terms` 只用于刷新运行时 artifact 时做归并判断，不需要对普通用户暴露。

## 与现有对象的关系

| 对象 | 作用 | 粒度 |
| --- | --- | --- |
| `topic` | 用户长期关注面 | 最大 |
| `thread` | 某条持续发展的thread | 中间层 |
| digest item | 某次简报里的单条发现 | 最细 |

建议关系是：

1. ingest / digest 先发现当天的重要简讯。
2. 如果它属于某条已存在的持续事件，就把它挂到对应 `thread`。
3. 当天 digest 里可以继续输出这条简讯，但表述上应该让用户感知到它是“这条线的新进展”。
4. deep-analysis 可以既支持“第 3 条”，也支持“展开比亚迪闪充站这条线”。

每个 active Thread 都独立展示。最新进展逐条保留真实新闻，不压成一句概述。历史展示只选跨完整生命周期的重要节点，不把全量报道搬进日报。

```markdown
## 事件线时间线更新

### T-01 比亚迪闪充站

**最新进展**：
- **2026-04-27** · [首批落地城市名单发布](https://example.com/cities) · N-01
正式名单明确覆盖城市与建设进度。
点评：讨论重点从技术发布转到交付兑现。

**历史时间线**：
- [技术方案正式发布](https://example.com/launch) ｜ 2026-04-01
- [首批城市公布](https://example.com/cities) ｜ 2026-04-27

无增量时写明本轮暂无可核验新增，并展示最新已知状态和下一步观察。
```

原始 `timeline` 全量追加、去重并保留未知字段。展示层只读取有具体 `milestone_reason`、有效来源 URL 和真实日期的节点。恢复日期另写 `milestone_date` 和 `milestone_date_basis`，不以采集日期代替事件日期。

`dig: T-01` 和 `write: T-01` 读取完整历史，前者分析脉络，后者生成有来源的文章草稿，不自动发布。新闻使用 `dig: N-01` 和 `track: N-02`，另支持自然语言反馈。这五项构成固定操作区，不展示版本、模型、执行日志或投递结论。

每份正式 digest 同步保存不可变 `.events.json` 编号快照。收到卡片后，优先按被回复的 message_id 查询该绑定的快照，没有 message_id 才使用同绑定最近完整成功投递的快照。新生成但未送达的日报不得改变旧卡片的编号含义。历史节点投影和最新进展都不改变底层原档。

## 当前事件集与完整历史

采集和外部检索结果都使用 `skrya.ingest.v2`。外部搜索工具 API 不变，Skrya 与智能体负责适配结果。条目保留熟悉的 `items` 字段，并带有 `source_id`、`event_id`、`content_hash`，批次记录 `source_generations`。事件身份按来源和原始文章 URL 确定；无 URL 时使用规范化标题，内容哈希覆盖规范化标题、摘要和正文。存储的文章 URL 不被重写。

`runs/<topic-id>/event-state.json` 保存来源 generation 和事件索引。成功的非预览采集推进该来源的 generation，成功解析缓存也算一次成功采集；失败、跳过和预览不推进。当前事件集只取各来源最新 generation，旧记录仍保留。这不是删除历史，也不是网络请求计数。

日报只隐藏最近三份正式 `.events.json` 快照中 `event_id` 和 `content_hash` 都相同的内容。身份相同但内容变化的报道可再次出现。预览不写快照或去重记忆。隐藏重复新闻不等于关闭 Thread，每个 active Thread 仍须展示，无增量时说明最新已知状态和下一步观察。完整原始 `timeline` 继续用于 `dig: T-01` 和 `write: T-01`。

旧版当前 ingest 须显式运行 `upgrade --migrate-ingest-v2` 并保留当前文件备份。已冻结日报、编号快照、投递回执、旧 ingest 归档和 Thread 原始历史都不改写。旧 v1 日报快照仍可解析原编号。清理仅通过 `ingest-prune` 显式执行，先 dry-run，再审阅并使用 `--apply`；只删除符合条件的 ingest 批次，不触碰 Thread 历史。命令见[升级说明](upgrade.md)。

## 用户旅程示例

以 `topic = 新能源汽车`、`thread = 比亚迪闪充站` 为例：

1. 用户先建立长期 topic：关注新能源汽车的重要动态。
2. agent 在多天简报里反复看到“比亚迪闪充站发布、首批城市、合作建设、体验反馈”等相关进展。
3. 当这类简讯开始连续出现时，agent 应把它们识别为同一条持续thread，而不是每天重写一个新标题。
4. 之后的日报应该用 2-4 行具体说明，而不是只写“这条线今天又有推进”。例如：首批城市名单的变化、实测补能效率是否出现更多独立来源、后续还要盯什么。
5. 用户如果说“展开这条线”，agent 就应该按时间线回放，而不是只分析最新一条新闻。

如果你想看这条能力在面向普通用户时的完整对话顺序，可以继续看 [`user-journeys.md`](./user-journeys.md) 里的“旅程 6：持续事件的时间线追踪”。

## 示例文件

仓库里附了一个结构化示例：[`byd-flash-charge-thread.example.json`](./byd-flash-charge-thread.example.json)。

另外还附了一个 seed 示例：[`byd-flash-charge-thread-seed.example.json`](./byd-flash-charge-thread-seed.example.json)。

如果你想看它在示例 topic 目录里的最小落点，可以直接参考仓库 fixture `tests/fixtures/topics/new-energy-vehicles/`：这里把 `topic.json`、`brief.json`、`sources.json`、`sample-events.json` 和 `thread-seeds.json` 放在了一起，方便同时理解“topic 边界”和“thread边界”。真实用户数据应放在 Skrya data root 下。

当前版本已经支持：

1. 用 `python -m skrya_orchestrator.main digest --topic new-energy-vehicles --root . --data-root tests/fixtures --sample` 基于示例事件生成日报，并同步写出运行时 `latest-threads.json`。
2. 用 `python -m skrya_orchestrator.main refresh-threads --topic new-energy-vehicles --root . --data-root tests/fixtures` 把 `thread-seeds.json` 和 `latest-digest-events.json` 手动刷新成运行时 `latest-threads.json`。
3. 用 `python -m skrya_orchestrator.main thread --topic new-energy-vehicles --thread "比亚迪闪充站" --root . --data-root tests/fixtures` 按时间线回放这条thread。

当前版本还**不会**在没有 seed 的情况下自动发现一条新thread；“要不要新建这条线、这条线应该叫什么”仍然需要先由 agent 或维护者给出明确种子。
