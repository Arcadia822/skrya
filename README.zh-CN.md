<div align="center">

# Skrya

**把“每天帮我关注这个方向”变成可长期运行的 AI 简报。**

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
![Skrya](https://img.shields.io/badge/skrya-v0.1.0-0ea5e9.svg)

**简体中文** · [English](README.md)

</div>

Skrya 是一个给 AI 智能体用的简报技能包。用户只需要说清楚想长期关注什么，智能体负责把它变成一个稳定的主题：确认范围、确认信源、创建定时任务、生成每日简报、接受反馈、持续修正。

## 它最后长什么样

```text
用户：每天帮我追踪 AI 浏览器重要动态。

Skrya 会把它变成：
1. 主题范围：AI 浏览器、浏览器智能体、搜索/浏览器入口变化
2. 信源策略：官方发布、主流科技媒体、产品更新、社交信号分层确认
3. 定时简报：每天在原会话投递，失败时说明缺失前提
4. 每日简报：统一格式、紧凑来源、可继续深挖
5. 后续事件线：对同一条持续事件线接着讲，而不是每天重开标题
```

```markdown
# 2026-05-08｜AI 浏览器｜每日简报

### N-01 OpenAI 浏览器入口传闻升温
判断：浏览器成为智能体执行入口后，身份、工具调用和网页状态会被放进同一个工作流。
信源：[OpenAI：ChatGPT Atlas](https://openai.com/index/introducing-chatgpt-atlas/) | [OpenAI：ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/) | [The Verge](https://www.theverge.com/news/802765/openai-chatgpt-atlas-browser-agent)

### N-02 Perplexity、Arc 等产品融合搜索、浏览和智能体操作
判断：AI 浏览器改变搜索分发、网页操作和个人上下文的组织方式。
信源：[Perplexity：Comet](https://www.perplexity.ai/comet) | [Arc：Browser](https://arc.net/) | [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)

---

## 可继续操作

- 回复 `dig: N-01`，深挖指定新闻。
- 回复 `track: N-02`，建立持续事件线。
- 回复 `dig: T-01`，查看事件线的全量历史。
- 回复 `write: T-01`，生成有来源的文章草稿，不自动发布。
- 自然语言反馈，例如低质量传闻少推。
```

查看更多演示：[AI 浏览器每日简报](examples/ai-browser-daily-briefing.md)、[新能源事件线](examples/new-energy-thread-demo.md)、[研究智能体观察清单](examples/research-agent-watchlist.md)。

简报的标题、条目、信源和操作区都来自模板。创建从默认合同起草新候选，更新读取已有模板；两者保存前都检查 active Thread、真实日期与来源、固定五项操作等合同，失败不创建或覆盖目标。飞书支持原生卡片、摘要加线程与完整分片，详见[原生通道投递](docs/channel-adapters.md)。渲染完成不等于消息已送达。

## 30 秒开始

把这句话发给你的智能体：

```text
请安装 Skrya：https://github.com/Arcadia822/skrya 。安装后，帮我每天关注 AI 浏览器的重要动态。
```

智能体会读取仓库里的安装说明完成安装。你不需要手动复制命令。安装后，它应该先确认你真正想看的内容，再确认信源和投递方式。它不应该立刻丢一堆搜索结果给你。这种克制目前仍然算进步。

也可以手动安装：

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
./setup --host auto
```

## 核心能力

### 每日简报

把长期关注的方向变成稳定、可复用的每日简报。每条信息都带来源、判断和后续可操作入口。

### 信源把关

在创建任务前先确认信源。Skrya 会区分能自动接入的来源、需要运行时检索的来源、暂时不能自动接入的来源。

直接 RSS、Atom 和 RSSHub 路由由 Skrya 自己采集、解析并规范化为 `skrya.ingest.v2`。智能体已有的外部搜索工具 API 不变，结果适配和规范化由 Skrya 与智能体负责。已确认的 RSSHub 来源拉取失败时，运行时请求会交给智能体，通过中立的网页或新闻检索覆盖同一个已确认来源，不编造文章 URL，也不静默换源。

`source-curation/presets/` 提供 AI/LLM、科技新闻、开发者工具、新能源汽车、加密货币五类候选，以及 RSSHub 路由目录。它们只是选源参考，不代表已接入或当前可达。启用前仍须确认来源并实时探测；RSSHub 还须确认实例、路由，以及备用检索能力和查询。未配置备用方案的旧来源会按来源名、路由和主题需求生成中立检索请求，不修改长期来源配置。

### 组合扩展

Skrya 会自主寻找本地可用的技能，尽量扩大信源覆盖。比如用 `agent-reach` 扩展公开网页与社交检索，用 `wechat-article-search` 补微信公众号文章。Skrya 不关注绕过登录墙或访问限制的手段，只负责把可用信源组织成可复用的简报流程。

### 持续事件线

同一件事不会每天被拆成互不相关的新标题。Skrya 会把持续发展的事件串成事件线，方便回看上下文。

### 反馈会变成记忆

你说“这类少推”“这条继续跟”“展开第 3 条”，Skrya 会把反馈转成后续简报的长期偏好，而不是只在当前聊天里回应。

### 重复内容与本地缓存

同一 `event_id` 和 `content_hash` 已出现在最近三份正式日报的 `.events.json` 快照中时，本轮隐藏这条重复内容；内容变化后可以再次出现。预览不改变这份记忆。`event_id` 来自 `source_id` 和原始文章 URL；没有 URL 时使用规范化标题。`content_hash` 来自规范化后的标题、摘要和正文，不改写保存的文章 URL。

每个来源成功完成非预览采集后，独立推进 generation；成功解析缓存响应也算成功采集，不代表发生了新网络请求。失败、跳过和预览不推进。最新 generation 定义当前事件集，旧记录和完整 Thread 原始历史继续保留。当前状态保存在 `runs/<topic-id>/event-state.json`。旧版 `skrya.ingest.v1` 当前文件必须显式运行 `upgrade --migrate-ingest-v2`，转换前会备份，详见[升级说明](docs/upgrade.md)。

HTTP 缓存支持采集时的条件请求和新鲜度判断，中文翻译使用不过期的内容哈希缓存。`digest --force-refresh` 仅绕过本轮 HTTP 缓存新鲜度。`cache` 无须 topic，只维护已识别的缓存条目，可用 `--clear-http-cache`、`--clear-translation-cache --translation-language zh-CN` 或 `--cleanup-expired`；不传操作参数只显示用法，不清理任何内容。预览不会改变 data root 中的任何文件。

来源健康状态保存在 topic 目录中。连续失败会触发降级和临时退避，`source-health --topic <topic-id>` 只读报告，`--refresh` 为该主题采集一次。健康提示放在日报首个章节之前，不另加第六项操作。真实来源失败时不会静默改用样例。

`ingest-prune --topic <topic-id> --keep 10` 默认只报告将删除的归档批次。先审阅选择，再加 `--apply` 才删除对应 raw/normalized ingest 文件。最新引用批次始终受保护；日报、编号快照、Thread、投递回执和绑定都不删除。

### 通道不串台

在有 channel/conversation 的 host 里，哪个通道创建的日报，就默认发回哪个通道。补发和空日报诊断也只处理当前通道绑定的内容。

## 语言

安装 Skrya 时不需要指定语言。语言跟着主题走：

- 新建主题时，默认使用你创建主题时的语言。
- 你也可以明确要求某个主题用中文或英文输出。
- 当前只支持中文和英文输出。
- 你后续用什么语言反馈，智能体就用什么语言和你交流；除非你明确要求，否则不会改变主题的简报语言。

## 隐私

Skrya 完全本地运作，不包含遥测、云同步或托管后端，不会主动上传你的主题配置、历史简报、反馈偏好或本地数据。你让智能体组合使用的联网检索、浏览器、微信公众号检索等其他技能，会按那些技能自己的规则访问外部来源。

## 卸载

Skrya 支持三种卸载方式：

| 模式 | 删除 | 保留 |
| --- | --- | --- |
| `skills-keep-data` | 已安装技能 | 主题配置、历史简报、数据配置 |
| `data-keep-skills` | Skrya 数据和数据配置 | 已安装技能 |
| `complete` | 技能、数据、全局指令里的 Skrya 路由说明 | 无关用户指令 |

对智能体说：

```text
卸载 Skrya。先告诉我三种卸载模式的区别，然后等我确认再执行。
```

完全卸载只会移除带 `SKRYA-ROUTING-NOTE` 标记的 Skrya 全局指令块，不应该清空整份 `AGENTS.md`、`CLAUDE.md`、`TOOLS.md` 或 `tools.md`。

## 更多文档

| 文档 | 内容 |
| --- | --- |
| [安装说明](INSTALL.md) | 给智能体读取的安装、卸载和升级步骤 |
| [用户旅程](docs/user-journeys.md) | 智能体面向普通用户时应该怎么行动 |
| [事件线](docs/threads.md) | 如何持续跟踪同一条事件线 |
| [通道绑定](docs/delivery-bindings.md) | 如何把主题投递隔离在创建它的通道和用户上下文里 |
| [信源健康](docs/source-health.md) | 连续失败、退避与诊断 |
| [HTTP 缓存](docs/http-cache.md) | 持久化缓存与条件请求 |
| [翻译缓存](docs/translation-cache.md) | 中文输出的内容哈希缓存 |
| [外部检索接口](docs/external-retrieval-interface.md) | 如何接入运行时检索结果 |
| [领域模型](docs/domain-model.md) | 主题、请求、信源、事件线、通道等实体 |
| [贡献指南](CONTRIBUTING.md) | 开发、测试、代码结构和技术设计 |

## 许可证

[MIT](LICENSE)
