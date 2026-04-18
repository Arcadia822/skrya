# 核心 Skill 行为规格

## 目标

Skrya 当前围绕 5 个核心 skill 组织 topic-driven 工作流：

- `topic-curation`
- `request-curation`
- `source-curation`
- `digest`
- `deep-analysis`

其中：

- `topic-curation` 是用户面对的总入口
- `request-curation` 和 `source-curation` 是更窄的配置职责
- `digest` 和 `deep-analysis` 是日常消费层能力

这组 skill 已经足够支撑一个 topic 从需求澄清到持续使用的完整路径。

## 全局规则

所有 skill 都必须遵守这些仓库级约束：

1. 任何 topic 相关任务都必须显式指定 `topic-id`。
2. 只允许在对应 topic 的目录边界内修改 topic 文件。
3. 如果要改文件，必须先说明将要修改什么。
4. 需要人判断的建议，必须先确认再写入文件。
5. 正常输出默认不展示 source list，不把正文写成调试输出。
6. 如果用户明确追问来源，系统必须能补充返回对应 source。

## Skill 分层

### 1. Topic Entry Layer

`topic-curation` 负责接住广义追踪请求，尤其是这些情况：

- 用户还没有现成 `topic-id`
- 用户说“帮我持续跟踪某个公司、行业或主题”
- 用户在用自然语言描述一类长期想看的信息

这个 skill 的核心职责，是先把长期追踪意图聊清楚，再决定是否要创建或修改 topic 文件。

### 2. Configuration Layer

`request-curation` 负责把用户反馈转成稳定的 `brief.json` 语义，例如：

- 多看什么
- 少看什么
- 排名偏好如何调整
- 哪类条目要排除

`source-curation` 负责在 topic intent 已经明确后，决定 `sources.json` 应该如何变化。当前信源规则保持简单：

- 有 RSS，可接入
- 没有 RSS，当前不可接入

### 3. Consumption Layer

`digest` 负责把 topic 当前最值得看的事件整理成统一编号的单段落列表。

`deep-analysis` 负责围绕 digest 编号继续做事件重建、可信度判断和后续观察。

## Source Of Truth

Skill 文案和宿主包装不再直接以 `skills/` 为真相源。

应该这样理解目录：

- `skills-src/`：skill 源模板与元数据
- `prompt-templates/`：thin prompt pack 源模板
- `skills/`：workspace 默认生成结果
- `.agents/skills/`、`.claude/skills/`、`.openclaw/skills/`：不同宿主的生成结果
- `agent-hosts/`：不同宿主使用的 `skrya-lite` / `skrya-full` / `skrya-plan`

如果改的是 agent 行为，应优先编辑源模板，再运行生成命令，而不是手改生成目录。

