# Skrya

Skrya 是一个 `topic-driven briefing workspace`。

它不是泛资讯后台，也不是简单的信息源列表，而是围绕显式的 `topic-id` 持续追踪主题，生成可继续追问的中文 digest，并支持按 digest 编号继续做单事件深挖。

## 仓库结构

核心目录：

- `topics/<topic-id>/`：主题配置与判断标准
- `runs/<topic-id>/`：最近一次 digest 和分析产物
- `skills-src/`：agent skill 的 source-of-truth
- `skills/`：workspace 默认生成出来的 skill 产物
- `prompt-templates/`：`skrya-lite` / `skrya-full` / `skrya-plan` 的源模板
- `agent-hosts/`：面向不同宿主生成出来的 prompt pack
- `design/`：系统设计、样例和规范文档
- `src/skrya_orchestrator/`：本地 CLI、digest/deep-analysis 逻辑和 agent asset builder

一个标准 topic 默认包含这些文件：

- `topic.json`
- `brief.json`
- `sources.json`
- `digest.md`
- `deep-analysis.md`

## 快速开始

安装：

```powershell
python -m pip install -e .
```

生成某个 topic 的 digest：

```powershell
python -m skrya_orchestrator.main digest --topic k-entertainment --root .
```

基于 digest 编号继续深挖：

```powershell
python -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root .
```

重新生成多宿主 agent 资产：

```powershell
python -m skrya_orchestrator.main build-agent-assets --root . --host all
```

运行后会在 `runs/<topic-id>/` 下生成：

- `latest-digest.md`
- `latest-digest-events.json`
- `deep-analysis-<number>.md`

## Skill 组织方式

当前核心 skill 拆成 5 个职责单元：

- `topic-curation`：用户面对的总入口，负责把广义追踪需求收束成可执行 topic
- `request-curation`：把“以后多看什么、少看什么”的反馈沉淀到 `brief.json`
- `source-curation`：在 topic intent 已经清楚后，决定哪些 RSS 信源应进入 `sources.json`
- `digest`：把 topic 当前值得看的事件整理成编号 digest
- `deep-analysis`：围绕 digest 项目编号继续做单事件深挖

其中 `topic-curation` 仍然是广义入口；`request-curation` 和 `source-curation` 是更窄的职责层，便于不同 agent 清楚各自边界。

## Source Of Truth 与生成物

如果你要修改 agent 能力，不要直接手改生成产物。

- 编辑 `skills-src/` 和 `prompt-templates/`
- 运行 `build-agent-assets`
- 让生成器刷新这些目录：
  - `skills/`
  - `.agents/skills/`
  - `.claude/skills/`
  - `.openclaw/skills/`
  - `agent-hosts/`

这套结构的目标，是让 Codex、Claude Code、OpenClaw 一类宿主都能消费同一份 Skrya 方法论，而不是各自维护一份会漂移的 prompt。

## 工作方式

这套工作区默认遵循这些产品约束：

- 任何 topic 相关任务都必须显式指定 `topic-id`
- 默认优先使用真实数据
- 默认输出中文
- 正常输出里不内联 source list
- digest 里的每条内容都用统一编号，方便用户直接回复数字继续分析

如果用户还没有现成 topic，而是先说“帮我持续跟踪某个公司、行业或主题”，应该先走 `topic-curation`，把长期追踪意图澄清清楚，再去生成 digest。

## 设计文档

如果你要快速理解系统边界，优先看这些文件：

- [current-system-design.md](D:/Documents/skrya/design/current-system-design.md)
- [core-skills-spec.md](D:/Documents/skrya/design/core-skills-spec.md)
- [digest-spec.md](D:/Documents/skrya/design/digest-spec.md)
- [deep-analysis-spec.md](D:/Documents/skrya/design/deep-analysis-spec.md)
- [2026-04-18-skrya-agent-host-bridge-design.md](D:/Documents/skrya/docs/superpowers/specs/2026-04-18-skrya-agent-host-bridge-design.md)

## 测试

```powershell
python -m unittest discover -s tests -v
```

