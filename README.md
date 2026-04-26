# Skrya

> Topic-driven briefing workspace for agent-native daily digests, source curation, and event follow-up.

[![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
[![Agent Skill Pack](https://img.shields.io/badge/Agent_Skill_Pack-Skrya-0ea5e9.svg)](#核心能力)
[![Tests](https://img.shields.io/badge/tests-unittest-10b981.svg)](#开发与测试)
[![Host](https://img.shields.io/badge/hosts-Codex%20%7C%20Claude%20%7C%20OpenClaw-6b7280.svg)](#兼容宿主)

Skrya 是一个面向 agent 的多主题信息追踪与简报工作区。它把用户的自然语言关注需求，沉淀成可持续运行的 topic 配置，再由 agent 完成来源接入、事件筛选、日报生成、深度分析和持续事件线追踪。

不是传统 RSS 阅读器，也不是固定后台服务。Skrya 更像一套可迁移的 briefing workflow：用户只说“以后每天帮我关注什么”，agent 负责把它变成可复用、可自动化、可跨宿主安装的配置和技能包。

---

## 目录

- [解决什么问题](#解决什么问题)
- [核心能力](#核心能力)
- [15 秒上手](#15-秒上手)
- [日报输出示例](#日报输出示例)
- [Topic 模型](#topic-模型)
- [持续事件线](#持续事件线)
- [外部检索接口](#外部检索接口)
- [安装](#安装)
- [常用命令](#常用命令)
- [项目结构](#项目结构)
- [开发与测试](#开发与测试)
- [Source of Truth](#source-of-truth)
- [GitHub 元信息建议](#github-元信息建议)

## 解决什么问题

信息追踪的痛点通常不是“没有信息源”，而是缺少稳定判断层：

| 常见问题 | Skrya 的处理方式 |
| --- | --- |
| 用户只会说“帮我关注这个方向” | `topic-curation` 把自然语言转成长期 topic 配置 |
| 每天内容太碎，难判断重要性 | `digest` 按 topic 偏好筛选、排序、生成简报 |
| 用户反馈只停留在聊天里 | `request-curation` 把“多推/少推/别推”写成持久偏好 |
| 某件事连续发酵但每天标题都不同 | `event-thread` 把相关简讯串成持续事件线 |
| 第三方检索工具不稳定 | `runtime-retrieval` 只记录能力，不绑定供应商名称 |

## 核心能力

| Skill | 作用 |
| --- | --- |
| `topic-curation` | 创建或调整长期关注主题 |
| `request-curation` | 把日报反馈沉淀成稳定偏好 |
| `source-curation` | 管理自动接入来源和运行时检索能力 |
| `digest` | 生成带信源、编号、系统提示的主题日报 |
| `deep-analysis` | 对某条简讯做脉络、可信度和后续观察分析 |

根 `skrya` skill 负责把用户请求路由到正确 workflow。普通用户不需要知道这些 skill 名称；它们是 agent 的内部执行层。

## 15 秒上手

非技术用户可以直接这样说：

```text
以后每天帮我关注 AI 浏览器有什么重要动态。
```

```text
这条以后少推，类似的轻量榜单不用放日报里。
```

```text
展开第 3 条，帮我判断这件事后面还值不值得看。
```

```text
帮我持续跟比亚迪闪充站这条线；以后有新进展就接着往下讲。
```

Agent 的默认流程：

1. 先确认用户真正想长期追踪的内容。
2. 把关注意图写入 topic 配置。
3. 讨论是否创建每日自动简报。
4. 用户确认后试跑一次日报。
5. 后续把用户反馈沉淀成长期偏好。

## 日报输出示例

Skrya 的默认日报现在分为主体内容和系统提示。大标题包含执行日期和主题，简讯结束后用分割线进入系统提示区。

```markdown
# 2026-04-26｜新能源汽车｜每日简报

## 事件线更新

┌─ **【事件线】比亚迪闪充站**
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
- 执行状态：完成：生成 3 条简讯，更新 1 条事件线。
- 扫描时间范围：最近 24 小时（默认）
- 可继续操作：
  - A. 详细分析指定今日简讯，例如：`A 3 5 12`。
  - B. 创建新的事件线，例如：`B 3 4 5 持续关注`。
  - C. 调整简讯和事件线的获取策略，例如：`C 6 7 我不喜欢，如果是 xxx 不要关注`。
```

## Topic 模型

每个 topic 是一个独立目录，存放在 Skrya data root 下面。默认 data root 是 `~/.skrya`；OpenClaw、容器沙盒或明确要求挂载目录的环境可以使用当前 workspace 的 `.skrya/data`。

```text
<skrya-data-root>/topics/<topic-id>/
  topic.json
  brief.json
  sources.json
  digest.md
  deep-analysis.md
  event-thread-seeds.json  # 可选
```

| 文件 | 用途 |
| --- | --- |
| `topic.json` | 主题身份、显示名和描述 |
| `brief.json` | 用户真正关心什么 |
| `sources.json` | 自动接入来源和运行时检索能力 |
| `digest.md` | 日报排序、排除和呈现标准 |
| `deep-analysis.md` | 深度分析判断标准 |
| `event-thread-seeds.json` | 持续事件线的名称、别名和匹配边界 |

这些文件名默认不暴露给普通用户。它们是 agent 的执行细节，和许多执行细节一样，最好保持安静。

## 持续事件线

`event-thread` 是位于 topic 之下、单条 digest item 之上的轻量实体，用来追踪会连续发展的事件。

典型流程：

1. 用户说：“新能源汽车这个 topic 里，帮我持续跟比亚迪闪充站这条线。”
2. Agent 在 `<skrya-data-root>/topics/new-energy-vehicles/event-thread-seeds.json` 稳定这条线的名字、别名和匹配边界。
3. 生成日报时，如果今日简讯命中 seed，Skrya 写出运行时事件线产物：`<skrya-data-root>/runs/new-energy-vehicles/event-threads/latest-event-threads.json`。
4. 用户说“展开这条线”时，Skrya 按时间线回放。

运行时产物：

```text
<skrya-data-root>/runs/<topic-id>/event-threads/
  latest-event-threads.json
```

参考示例：

- Fixture topic: `topics/new-energy-vehicles/`
- 设计说明: [docs/event-threads.md](docs/event-threads.md)
- 用户旅程: [docs/user-journeys.md](docs/user-journeys.md) 里的“旅程 6：持续事件的时间线追踪”

## 外部检索接口

Skrya 支持使用第三方检索 skill，但不会把具体供应商写成长期依赖。长期配置只记录能力：

- `web_search`
- `news_search`
- `site_search`
- `social_search`
- `document_fetch`

运行流程：

```text
Skrya retrieval request
  -> 当前 agent 选择可用检索工具
  -> 归一化为 skrya.ingest.v1
  -> digest 只消费归一化 ingest
```

运行产物：

```text
<skrya-data-root>/runs/<topic-id>/ingest/
  latest-ingest.json
  normalized/
  raw/
```

接口详情见 [docs/external-retrieval-interface.md](docs/external-retrieval-interface.md)。

## 安装

要求 Python 3.10+。如果本机没有 `python` 命令，请使用 `python3`。

### 在仓库内生成全部 host 产物

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

### 自动安装到当前机器的默认宿主

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

`install-skill-pack` 会检测 `~/.codex`、`~/.claude`、`~/.openclaw`。如果都不存在，默认回退到 Codex 安装路径。

### 显式指定宿主

```bash
python3 -m skrya_orchestrator.main install-skill-pack --root . --host codex
python3 -m skrya_orchestrator.main install-skill-pack --root . --host claude
python3 -m skrya_orchestrator.main install-skill-pack --root . --host openclaw
```

便捷脚本：

```bash
./setup --host auto
```

PowerShell:

```powershell
./setup.ps1 --host auto
```

### 数据位置

安装 skill 时会同时配置 Skrya data root，也就是长期 topic 配置和历史运行产物的位置。

默认策略：

- `codex` / `claude`：使用 `~/.skrya`
- `openclaw`：使用当前 workspace 的 `.skrya/data`
- 显式环境变量 `SKRYA_DATA_ROOT` 或 CLI `--data-root` 会覆盖配置

常见安装方式：

```bash
./setup --host codex --data-root-mode home --migrate-data
./setup --host openclaw --data-root-mode workspace --migrate-data
./setup --host codex --data-root-mode custom --data-root-path /path/to/skrya-data --data-root-config-scope home
```

查看或修改 data root：

```bash
python3 -m skrya_orchestrator.main data-root --root .
python3 -m skrya_orchestrator.main data-root --root . --set .skrya/data --scope workspace --migrate
```

`--migrate` / `--migrate-data` 会把已有 workspace 里的 `topics/` 和 `runs/` 复制到新 data root；它不会删除旧数据。

## 兼容宿主

| 宿主 | 指令文件 | 全局安装 | 说明 |
| --- | --- | --- | --- |
| `workspace` | `AGENTS.md` | 不提供 | 仓库内生成提示词；topic 数据由 data root 决定 |
| `codex` | `AGENTS.md` | 支持 | 兼容 `~/.codex/skills/` |
| `claude` | `CLAUDE.md` | 支持 | 兼容 `~/.claude/skills/` |
| `openclaw` | `AGENTS.md` | 支持 | 兼容 `~/.openclaw/skills/` |

## 常用命令

下面的命令用仓库内 checked-in fixture 试跑，所以显式加了 `--data-root .`。真实安装后的长期数据默认读取 `~/.skrya`，通常不需要这个参数。

生成日报：

```bash
python3 -m skrya_orchestrator.main digest --topic k-entertainment --root . --data-root .
```

使用内置样例试跑：

```bash
python3 -m skrya_orchestrator.main digest --topic new-energy-vehicles --root . --data-root . --sample
```

继续分析某条日报事件：

```bash
python3 -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root . --data-root .
```

按时间线回放持续事件线：

```bash
python3 -m skrya_orchestrator.main event-thread --topic new-energy-vehicles --thread "比亚迪闪充站" --root . --data-root .
```

根据最新 digest artifact 刷新事件线运行时产物：

```bash
python3 -m skrya_orchestrator.main refresh-event-threads --topic new-energy-vehicles --root . --data-root .
```

生成 provider-neutral 检索请求：

```bash
python3 -m skrya_orchestrator.main retrieval-request --topic k-entertainment --root . --data-root .
```

记录归一化 ingest：

```bash
python3 -m skrya_orchestrator.main ingest --topic k-entertainment --root . --data-root . --file runs/k-entertainment/ingest/input.json
```

重建 skill pack：

```bash
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

## 项目结构

```text
.
  skill-pack.json             # 根 skill 元数据
  SKILL.md.tmpl               # 根 skill 模板
  SKILL.md                    # 生成后的根 skill
  agents/openai.yaml          # 生成后的 agent metadata

  topic-curation/             # bundled skill
  request-curation/           # bundled skill
  source-curation/            # bundled skill
  digest/                     # bundled skill
  deep-analysis/              # bundled skill

  prompt-templates/           # host prompt pack 源模板
  topics/                     # checked-in 示例 topic，不是默认用户数据位置
  .skrya/                     # host prompt 产物；可含 workspace data root
  src/skrya_orchestrator/     # CLI、构建、安装、digest 和 ingest 实现
  tests/                      # 单元测试和契约测试
```

## 开发与测试

安装本地包：

```bash
python3 -m pip install -e .
```

运行测试：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

当前测试覆盖：

- skill pack 生成和安装
- topic 名称解析
- digest 排序与输出格式
- deep-analysis 编号解析和来源按需披露
- runtime retrieval / ingest 接口
- skill 文档契约

## Source of Truth

如果要改 agent-facing 行为，请先改源模板，再运行构建命令：

1. 根 skill：`skill-pack.json` 和 `SKILL.md.tmpl`
2. 子 skill：`<skill>/skill.json` 和 `<skill>/SKILL.md.tmpl`
3. host prompt：`prompt-templates/`
4. 构建：

```bash
python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

`.skrya/hosts/`、`.skrya/data/`、`runs/`、`tmp/`、`__pycache__/`、`*.egg-info/` 都是运行或缓存产物，不是 source of truth。长期用户数据默认在 `~/.skrya`，或由 `skrya data-root` 配置到 workspace。

## 设计文档

推荐先读：

- [design/current-system-design.md](design/current-system-design.md)
- [design/core-skills-spec.md](design/core-skills-spec.md)
- [design/digest-feedback-journey.md](design/digest-feedback-journey.md)
- [docs/external-retrieval-interface.md](docs/external-retrieval-interface.md)
- [docs/event-threads.md](docs/event-threads.md)
- [docs/user-journeys.md](docs/user-journeys.md)

## GitHub 元信息建议

Repository description:

```text
Topic-driven briefing workspace for agent-native daily digests, source curation, and event follow-up
```

Topics:

```text
agent-skill, briefing, daily-digest, topic-tracking, python, codex, claude, openclaw, retrieval, knowledge-workflow
```

## 贡献

欢迎提交 issue 和 PR。建议遵守以下原则：

- 先描述用户场景，再改配置或代码
- 新行为先补测试，尤其是 skill 契约测试
- 改 skill 文案时先改模板，再运行 `build-skill-pack`
- 不要把第三方检索 skill 写成 durable dependency
- 不要把 request id、内部文件名或抓取实现细节暴露给普通用户

## License

当前仓库尚未包含开源许可证文件。正式公开发布前建议补充 `LICENSE`，例如 MIT、Apache-2.0 或其他与你的发布目标匹配的许可证。
