# Skrya 当前系统设计

## 文档目的

这份文档描述 `skrya` 当前已经落地的系统设计，重点回答三件事：

1. 这个项目现在是什么。
2. 目录和能力是怎么组织的。
3. Agent-facing 资产是如何从 source-of-truth 生成出来的。

## 项目定位

`skrya` 是一个 `topic-driven` 的信息采集与分析工作区。

它不是传统资讯后台，也不是单纯的 RSS 阅读器。当前目标是：

- 围绕显式指定的 `topic-id`
- 优先使用真实数据
- 产出中文 digest
- 允许用户基于 digest 编号继续做单事件深入分析

第一条已经跑通的话题是 `k-entertainment`，但系统架构从一开始就是多 topic 可扩展的。

## 当前目录模型

### 主题配置

`topics/<topic-id>/` 下默认包含：

- `topic.json`
- `brief.json`
- `sources.json`
- `digest.md`
- `deep-analysis.md`

### 运行产物

`runs/<topic-id>/` 下默认包含：

- `latest-digest.md`
- `latest-digest-events.json`
- `deep-analysis-<number>.md`

### 核心代码

当前核心执行逻辑主要在：

- `src/skrya_orchestrator/intelligence.py`
- `src/skrya_orchestrator/main.py`
- `src/skrya_orchestrator/agent_assets.py`

也就是：

- 本地 digest / deep-analysis CLI
- agent asset builder

## Skill 与宿主组织

### Source Of Truth

Agent-facing 文案的真相源位于：

- `skills-src/`
- `prompt-templates/`

每个 skill source 目录包含：

- `skill.json`
- `SKILL.md.tmpl`

### 生成结果

生成命令：

```powershell
python -m skrya_orchestrator.main build-agent-assets --root . --host all
```

会刷新这些目录：

- `skills/`
- `.agents/skills/`
- `.claude/skills/`
- `.openclaw/skills/`
- `agent-hosts/`

### 宿主支持策略

第一版先支持 4 个宿主输出：

- `workspace`
- `codex`
- `claude`
- `openclaw`

当前的宿主适配策略保持轻量：

- 统一 skill source
- 统一 prompt pack source
- 不同宿主只改输出路径、指令文件名和 metadata 生成方式

这样做的目的，是先把“同一套方法论可以被多个 agent 消费”这件事跑通，再考虑更复杂的宿主适配。

## 工作流分层

工作流现在可以理解成三层：

1. `topic-curation`：接住广义追踪请求
2. `request-curation` / `source-curation`：把配置意图沉淀为 durable topic files
3. `digest` / `deep-analysis`：把 topic 转成可消费的日常输出

这种分层让人和 agent 都更容易判断：

- 现在是在定义 topic，还是在消费 topic
- 这次改动该写 `brief.json`、`sources.json`，还是只需要生成新的 digest

