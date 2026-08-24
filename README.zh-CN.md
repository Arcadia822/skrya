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

┌─ **【简讯1】OpenAI 浏览器入口传闻升温，重点不只是“做浏览器”**
│ 判断：如果浏览器成为智能体的执行入口，真正变化是身份、工具调用和网页状态会被放进同一个工作流。
│
│ 信源：[OpenAI：ChatGPT Atlas](https://openai.com/index/introducing-chatgpt-atlas/) [OpenAI：ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/) [The Verge：OpenAI launches ChatGPT Atlas](https://www.theverge.com/news/802765/openai-chatgpt-atlas-browser-agent)
└

┌─ **【简讯2】Perplexity、Arc 等产品继续把搜索、浏览和智能体操作揉在一起**
│ 判断：AI 浏览器不是一个单点功能，而是搜索分发、网页操作和个人上下文的重新打包。
│
│ 信源：[Perplexity：Comet](https://www.perplexity.ai/comet) [Arc：Browser](https://arc.net/) [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)
└

---

## 系统提示

- 可回复 `dig: 1` 深挖第 1 条。
- 可回复 `track: 2 AI 浏览器产品线` 把第 2 条变成持续事件线。
- 可直接回复 `低质量传闻少推` 调整后续简报偏好。
```

查看更多演示：[AI 浏览器每日简报](examples/ai-browser-daily-briefing.md)、[新能源事件线](examples/new-energy-thread-demo.md)、[研究智能体观察清单](examples/research-agent-watchlist.md)。

简报的标题、条目样式、来源展示和系统提示都来自模板；你可以直接要求 Skrya 调整模板，例如“把来源放到每条最后一行”或“系统提示写得更短”。进入模板更新时，Skrya 会先提示不可删除的 active Thread 时间线合同，并在保存前检查完整候选；检查失败不会覆盖现有模板。

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

### 组合扩展

Skrya 会自主寻找本地可用的技能，尽量扩大信源覆盖。比如用 `agent-reach` 扩展公开网页与社交检索，用 `wechat-article-search` 补微信公众号文章。Skrya 不关注绕过登录墙或访问限制的手段，只负责把可用信源组织成可复用的简报流程。

### 持续事件线

同一件事不会每天被拆成互不相关的新标题。Skrya 会把持续发展的事件串成事件线，方便回看上下文。

### 反馈会变成记忆

你说“这类少推”“这条继续跟”“展开第 3 条”，Skrya 会把反馈转成后续简报的长期偏好，而不是只在当前聊天里回应。

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
| [外部检索接口](docs/external-retrieval-interface.md) | 如何接入运行时检索结果 |
| [领域模型](docs/domain-model.md) | 主题、请求、信源、事件线、通道等实体 |
| [贡献指南](CONTRIBUTING.md) | 开发、测试、代码结构和技术设计 |

## 许可证

[MIT](LICENSE)
