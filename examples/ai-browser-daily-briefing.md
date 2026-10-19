# AI Browser Daily Briefing Demo

This is a public-facing demo of the shape Skrya tries to create. It is not a claim about today's live news. Real runs should use the topic's confirmed sources and execution-time links.

## User Request

```text
每天帮我追踪 AI 浏览器重要动态。
```

## Skrya Setup Flow

```text
Topic scope:
- AI 浏览器产品
- 浏览器里的智能体执行能力
- 搜索、分发和默认入口变化

Source policy:
- 自动接入：官方博客、产品发布页、RSS 可读的主流科技媒体
- 运行时检索：web/news search、X/social search、site search
- 暂时不能自动接入：无公开 feed、需要登录或只有人工截图传播的来源

Delivery:
- 每天投递到创建该 topic 的原会话或频道
- test run 需要用户单独确认
```

## Daily Digest Output

```markdown
# 2026-05-08｜AI 浏览器｜每日简报

### N-01 浏览器正在从网页容器变成智能体执行入口
判断：值得关注的是身份、网页状态、检索和工具调用是否被放进同一个工作流。
信源：[OpenAI：ChatGPT Atlas](https://openai.com/index/introducing-chatgpt-atlas/) | [OpenAI：ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/) | [The Verge](https://www.theverge.com/news/802765/openai-chatgpt-atlas-browser-agent)

### N-02 搜索产品继续向直接完成任务移动
判断：AI 浏览器和 AI 搜索的边界变薄，后续应看默认入口、插件生态和企业管控能力。
信源：[Perplexity：Comet](https://www.perplexity.ai/comet) | [Arc：Browser](https://arc.net/) | [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)

### N-03 浏览器智能体的安全边界开始成为产品差异点
判断：能否解释权限、隔离账号状态、避免跨站误操作，决定这类产品能否进入工作场景。
信源：[OpenAI：ChatGPT agent safety](https://openai.com/index/introducing-chatgpt-agent/) | [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)

---

## 可继续操作

- 回复 `dig: N-01`，深挖指定新闻。
- 回复 `track: N-02`，建立持续事件线。
- 回复 `dig: T-01`，查看全量历史。
- 回复 `write: T-01`，生成有来源的文章草稿，不自动发布。
- 自然语言反馈，例如少推没有来源的传闻。
```
