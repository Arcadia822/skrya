<div align="center">

# Skrya

**把“每天帮我关注这个方向”变成可长期运行的 AI 简报。**

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
![Skrya](https://img.shields.io/badge/skrya-v0.1.0-0ea5e9.svg)

**简体中文** · [English](README.en.md)

</div>

Skrya 是一个给 AI agent 用的简报技能包。用户只需要说清楚想长期关注什么，agent 负责把它变成一个稳定的 topic：确认范围、确认信源、创建定时任务、生成每日简报、接受反馈、持续修正。

## 30 秒开始

把这句话发给你的 agent：

```text
请安装 Skrya：https://github.com/Arcadia822/skrya 。安装后，帮我每天关注 AI 浏览器的重要动态。
```

Agent 会读取仓库里的安装说明完成安装。你不需要手动复制命令。安装后，它应该先确认你真正想看的内容，再确认信源和投递方式。它不应该立刻丢一堆搜索结果给你。这种克制目前仍然算进步。

## 核心能力

### 每日简报

把长期关注的方向变成稳定、可复用的每日简报。每条信息都带来源、判断和后续可操作入口。

### 信源把关

在创建任务前先确认信源。Skrya 会区分能自动接入的来源、需要运行时检索的来源、暂时不能自动接入的来源。

### 组合扩展

Skrya 会自主寻找本地可用的 skill，尽量扩大信源覆盖。比如用 `agent-reach` 扩展公开网页与社交检索，用 `wechat-article-search` 补微信公众号文章。Skrya 不关注绕过登录墙或访问限制的手段，只负责把可用信源组织成可复用的简报流程。

### 持续 thread

同一件事不会每天被拆成互不相关的新标题。Skrya 会把持续发展的事件串成 thread，方便回看上下文。

### 反馈会变成记忆

你说“这类少推”“这条继续跟”“展开第 3 条”，Skrya 会把反馈转成后续简报的长期偏好，而不是只在当前聊天里回应。

### 通道不串台

在有 channel/conversation 的 host 里，哪个通道创建的日报，就默认发回哪个通道。补发和空日报诊断也只处理当前通道绑定的内容。

## 语言

安装 Skrya 时不需要指定语言。语言跟着 topic 走：

- 新建 topic 时，默认使用你创建 topic 时的语言。
- 你也可以明确要求某个 topic 用中文或英文输出。
- 当前只支持中文和英文输出。
- 你后续用什么语言反馈，agent 就用什么语言和你交流；除非你明确要求，否则不会改变 topic 的简报语言。

## 隐私

Skrya 完全本地运作，不包含遥测、云同步或托管后端，不会主动上传你的 topic 配置、历史简报、反馈偏好或本地数据。你让 agent 组合使用的联网检索、浏览器、微信公众号检索等其他 skill，会按那些 skill 自己的规则访问外部来源。

## 卸载

Skrya 支持三种卸载方式：

| 模式 | 删除 | 保留 |
| --- | --- | --- |
| `skills-keep-data` | 已安装 skill | topic 配置、历史简报、数据配置 |
| `data-keep-skills` | Skrya 数据和数据配置 | 已安装 skill |
| `complete` | skill、数据、全局指令里的 Skrya routing note | 无关用户指令 |

对 agent 说：

```text
卸载 Skrya。先告诉我三种卸载模式的区别，然后等我确认再执行。
```

完全卸载只会移除带 `SKRYA-ROUTING-NOTE` 标记的 Skrya 全局指令块，不应该清空整份 `AGENTS.md`、`CLAUDE.md`、`TOOLS.md` 或 `tools.md`。

## 更多文档

| 文档 | 内容 |
| --- | --- |
| [安装说明](INSTALL.md) | 给 agent 读取的安装、卸载和升级步骤 |
| [用户旅程](docs/user-journeys.md) | agent 面向普通用户时应该怎么行动 |
| [thread](docs/threads.md) | 如何持续跟踪同一条事件线 |
| [外部检索接口](docs/external-retrieval-interface.md) | 如何接入运行时检索结果 |
| [领域模型](docs/domain-model.md) | topic、request、source、thread、channel 等实体 |
| [贡献指南](CONTRIBUTING.md) | 开发、测试、代码结构和技术设计 |

## License

[MIT](LICENSE)
