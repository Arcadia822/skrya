# Skrya

> 面向 agent 的 topic-driven 简报工作区：每日简报、信源确认、持续跟踪、深度分析和生命周期管理。

**语言 / Language:** 简体中文 | [English](README.en.md)

[![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
[![Agent Skill Pack](https://img.shields.io/badge/Agent_Skill_Pack-Skrya-0ea5e9.svg)](#skill-pack)
[![Tests](https://img.shields.io/badge/tests-unittest-10b981.svg)](#开发)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Skrya 把自然语言的信息跟踪需求变成可持续运行的 agent workflow。用户可以说“每天帮我关注 BYD、新能源汽车和储能”，agent 需要把它落实为确认过的 topic、信源计划、定时任务、测试简报、每日 digest、深度分析和长期反馈记忆。

它不是新闻客户端，也不是固定后台服务。它是一套让 agent 少一点即兴发挥、多一点可复用判断的技能包和运行时约定。令人意外地，这有助于减少事故。

## Skrya 解决什么

| 用户需求 | Skrya 行为 |
| --- | --- |
| “每天早上推送国内外 X 的官媒信息” | 先进入 topic 配置，而不是直接创建普通提醒。 |
| “有哪些信源？” | 先给出具体候选信源和可自动接入状态，再宣称配置完成。 |
| “测试一轮” | 使用正式 digest 模板输出预览，默认不保存为正式日报。 |
| “今天日报没有内容” | 排查生成、投递、通道绑定和空消息发送。 |
| “展开第 3 条” | 基于最新 digest index 做 deep analysis。 |
| “这条线持续跟” | 在 topic 下创建或更新 `thread`。 |
| “这类少推” | 写入长期偏好，而不是只在聊天里回应。 |
| “卸载 Skrya” | 提供只卸技能、只清数据、完全卸载三种模式。 |

## 核心概念

Skrya 是 topic-driven 的。主要实体包括：

- `topic`：一个长期关注主题。
- `request`：topic 内的用户意图、排序偏好和排除规则。
- `source`：确认过的信源，或 provider-neutral 的运行时检索能力。
- `digest item`：每日简报里的可见编号事件。
- `thread`：比 topic 更小、比单条 digest item 更稳定的持续时间线。
- `channel`：部分 host 暴露的会话/通道边界，用于定时投递隔离。
- `template`：setup、digest、test run、analysis 的输出契约。

完整实体图见 [docs/domain-model.md](docs/domain-model.md)，包括 `channel`、`delivery context`、`automation`、`run`、`ingest artifact` 和 `upgrade flow`。

## 语言策略

安装 Skrya 时不需要指定语言。语言是 topic 配置的一部分：

- 新建 topic 时，默认使用用户创建 topic 时使用的语言作为 `topic.json.language`。
- 用户也可以明确指定这个 topic 的简报输出语言。
- 当前项目只承诺中文和英文输出；schema 和框架保留未来扩展更多语言的空间。
- topic language 决定该 topic 的 digest 和 deep-analysis 输出语言。
- 用户后续反馈时，agent 与用户交流应使用用户反馈本身的语言；除非用户明确要求，否则不要顺手改变 topic 的输出语言。

## Skill Pack

根 `skrya` skill 负责把用户意图路由到子技能：

| Skill | 作用 |
| --- | --- |
| `topic-curation` | 创建或调整长期关注主题。 |
| `source-curation` | 确认候选信源和运行时检索能力。 |
| `request-curation` | 把 digest 反馈沉淀成长期偏好。 |
| `digest` | 生成带来源、编号和系统提示的每日简报。 |
| `deep-analysis` | 展开某条 digest item 或具体事件。 |

关键规则：

- topic 相关文件操作前必须解析内部 `topic-id`。
- 长期跟踪不能用一次性聊天搜索糊弄过去。
- 用户确认主题范围后，要先确认信源，再宣称接入和创建任务。
- 有 channel/conversation 的 host 默认把定时投递和补发绑定到创建通道。
- 测试简报必须使用正式模板，不在前后追加闲聊或保存路径。
- “每天推送 X 新闻”这类请求应先路由到 Skrya，而不是普通 automation。

## 用户流程

典型 setup：

1. 用户用自然语言描述长期关注需求。
2. Agent 确认 durable topic intent。
3. Agent 提出具体信源计划，并标注哪些可以自动接入。
4. 用户确认信源计划。
5. Agent 在 host 支持时创建或建议创建当前 channel 绑定的 recurring automation。
6. Agent 询问是否现在试跑一次。
7. 后续用户用 `A` / `B` / `C` 反馈触发深度分析、thread 或长期偏好更新。

示例：

```text
以后每天帮我关注 AI 浏览器有什么重要动态。
```

```text
帮我持续跟比亚迪闪充站这条线；以后有新进展就接着往下讲。
```

```text
展开第 3 条，帮我判断这件事后面还值不值得看。
```

## Digest 模板

每日简报使用稳定模板：标题、可选 thread 更新、统一 line box、紧凑来源引用，最后进入 `## 系统提示`。

```markdown
# 2026-04-26｜新能源汽车｜每日简报

## thread更新

┌─ **【thread】比亚迪闪充站**
│ 这条线从发布会概念走到建设兑现，讨论重点已经变成站点是否真的铺开。
│
│ 后续看点：首批站点在哪些城市真正落地；真实补能效率是否被反复验证。
└

## 今日简讯

┌─ **【简讯1】比亚迪闪充站首批落地城市名单开始清晰**
│ 这条线开始从产品能力展示推进到具体站点和城市铺设进度。
│
│ 信源：[example.com](https://example.com/byd-flash-charge-cities)
└

---

## 系统提示

- 执行时间：2026-04-26 12:19（Asia/Shanghai）
- 执行状态：完成：生成 3 条简讯，更新 1 条thread。
- 扫描时间范围：最近 24 小时（默认）
- Skrya：0.1.0
- 可继续操作：
  - A. 详细分析指定今日简讯，例如：`A 3 5 12`。
  - B. 创建新的thread，例如：`B 3 4 5 持续关注`。
  - C. 调整简讯和thread的获取策略，例如：`C 6 7 我不喜欢，如果是 xxx 不要关注`。
```

系统提示会包含 Skrya 版本。agent framework/version 和 LLM model 只有在 host 可见时才展示。

## Runtime Data

用户 topic 数据保存在 Skrya data root 下，不一定在本仓库里。

默认：

- 普通桌面 host：`~/.skrya`
- OpenClaw / container / mounted workspace：`.skrya/data`
- 覆盖方式：`SKRYA_DATA_ROOT` 或 `--data-root`

Topic 文件：

```text
<skrya-data-root>/topics/<topic-id>/
  topic.json
  brief.json
  sources.json
  digest.md
  deep-analysis.md
  thread-seeds.json
```

运行产物：

```text
<skrya-data-root>/runs/<topic-id>/
  latest-digest.md
  latest-digest-events.json
  ingest/latest-ingest.json
  threads/latest-threads.json
```

示例 topic 的 thread 路径：

```text
<skrya-data-root>/topics/new-energy-vehicles/thread-seeds.json
<skrya-data-root>/runs/new-energy-vehicles/threads/latest-threads.json
```

`thread` 设计见 [docs/threads.md](docs/threads.md)。示例 topic 在 [topics/new-energy-vehicles/](topics/new-energy-vehicles/)，包含 `thread-seeds.json`。回放时间线：

```bash
python3 -m skrya_orchestrator.main thread --topic new-energy-vehicles --thread "比亚迪闪充站" --root . --data-root .
```

完整对话流程见 [docs/user-journeys.md](docs/user-journeys.md)，尤其是“旅程 6：持续事件的时间线追踪”。

## Retrieval

Skrya 可以使用第三方检索工具，但长期配置只记录能力，不绑定 provider 名称：

- `web_search`
- `news_search`
- `site_search`
- `social_search`
- `document_fetch`

Provider 输出应先归一化为 `skrya.ingest.v1`；digest 和 deep analysis 只消费归一化产物，不直接消费 raw dump。接口见 [docs/external-retrieval-interface.md](docs/external-retrieval-interface.md)。

## 安装

要求 Python 3.10+。

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

安装 skill pack：

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

指定 host：

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host codex
python3 -m skrya_orchestrator.main install-skill-pack --root . --host claude
python3 -m skrya_orchestrator.main install-skill-pack --root . --host openclaw
```

便捷脚本：

```bash
./setup --host auto
./setup --host openclaw --data-root-mode workspace --migrate-data
```

PowerShell：

```powershell
./setup.ps1 --host auto
```

管理 data root：

```bash
python3 -m skrya_orchestrator.main data-root --root .
python3 -m skrya_orchestrator.main data-root --root . --set .skrya/data --scope workspace --migrate
```

`--migrate` 和 `--migrate-data` 会把已有 workspace `topics/` 和 `runs/` 复制到配置的 data root，不会删除旧文件。

## 卸载

Skrya 支持三种卸载模式。agent 应先解释选项，并在破坏性操作前确认。

| Mode | 删除 | 保留 |
| --- | --- | --- |
| `skills-keep-data` | 已安装 Skrya skill 目录和 bundled skill 链接 | topic 配置、运行历史、data-root config |
| `data-keep-skills` | Skrya data root 和 data-root config | 已安装 skill |
| `complete` | skill、Skrya 数据/config、全局指令文件中带标记的 Skrya routing note | 无关用户指令和非 Skrya 数据 |

命令：

```bash
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode skills-keep-data
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode data-keep-skills
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode complete
```

完全卸载只移除全局 instruction memory 里的 Skrya routing note。带 `SKRYA-ROUTING-NOTE` 标记的块可以安全自动删除；无关的 `AGENTS.md`、`CLAUDE.md`、`TOOLS.md`、`tools.md` 内容必须保留。

## 升级

更新已有安装前先读 [docs/upgrade.md](docs/upgrade.md)。

常用流程：

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main version --root . --check-latest
git pull --ff-only
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-thread-naming
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
PYTHONPATH=src python3 -m unittest discover -s tests
```

当前升级支持把旧 `event-thread` 运行时命名迁移到 `thread` 命名。旧文件会保留，用于审计和回滚。

## CLI Reference

下面示例使用 `--data-root .` 读取仓库 fixture。真实安装通常读取 `~/.skrya`。

```bash
python3 -m skrya_orchestrator.main digest --topic new-energy-vehicles --root . --data-root . --sample
python3 -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root . --data-root .
python3 -m skrya_orchestrator.main thread --topic new-energy-vehicles --thread "比亚迪闪充站" --root . --data-root .
python3 -m skrya_orchestrator.main refresh-threads --topic new-energy-vehicles --root . --data-root .
python3 -m skrya_orchestrator.main retrieval-request --topic k-entertainment --root . --data-root .
python3 -m skrya_orchestrator.main ingest --topic k-entertainment --root . --data-root . --file runs/k-entertainment/ingest/input.json
python3 -m skrya_orchestrator.main version --root . --check-latest
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode skills-keep-data
```

## 仓库结构

```text
.
  skill-pack.json
  SKILL.md.tmpl
  SKILL.md
  agents/openai.yaml

  topic-curation/
  request-curation/
  source-curation/
  digest/
  deep-analysis/

  prompt-templates/
  topics/new-energy-vehicles/
  docs/
  design/
  src/skrya_orchestrator/
  tests/
```

## Source Of Truth

改 agent-facing 行为时，先改源模板：

1. 根 skill：`skill-pack.json` 和 `SKILL.md.tmpl`
2. Bundled skills：`<skill>/skill.json` 和 `<skill>/SKILL.md.tmpl`
3. Host prompts：`prompt-templates/`
4. 重建产物：

```bash
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

生成的 `SKILL.md` 和 `agents/openai.yaml` 会提交到仓库，以便仓库可直接作为 skill pack 安装。`.skrya/hosts/`、`.skrya/data/`、`runs/`、`tmp/`、`__pycache__/`、`*.egg-info/` 是运行或缓存产物。

## 开发

```bash
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests
```

测试覆盖 skill-pack 生成、topic 解析、digest 格式、source curation、runtime retrieval、ingest normalization、thread timeline、upgrade、uninstall 和 skill 文档契约。

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。许可证为 [MIT](LICENSE)。
