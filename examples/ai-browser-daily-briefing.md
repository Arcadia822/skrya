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

┌─ **【简讯1】浏览器正在从“网页容器”变成智能体执行入口**
│ 判断：值得关注的不是某家公司是否发布独立浏览器，而是身份、网页状态、检索和工具调用是否被放进同一个工作流。
│
│ 信源：[OpenAI：ChatGPT Atlas](https://openai.com/index/introducing-chatgpt-atlas/) [OpenAI：ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/) [The Verge：OpenAI launches ChatGPT Atlas](https://www.theverge.com/news/802765/openai-chatgpt-atlas-browser-agent)
└

┌─ **【简讯2】搜索产品继续向“直接完成任务”移动**
│ 判断：AI 浏览器和 AI 搜索的边界会变得更薄，后续应持续看默认入口、插件生态和企业管控能力。
│
│ 信源：[Perplexity：Comet](https://www.perplexity.ai/comet) [Arc：Browser](https://arc.net/) [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)
└

┌─ **【简讯3】浏览器智能体的安全边界开始成为产品差异点**
│ 判断：能否解释权限、隔离账号状态、避免跨站误操作，会决定这类产品能否进入工作场景。
│
│ 信源：[OpenAI：ChatGPT agent safety](https://openai.com/index/introducing-chatgpt-agent/) [Perplexity：Comet Assistant](https://www.perplexity.ai/help-center/en/articles/11914212-comet-assistant)
└

---

## 系统提示

- 执行时间：2026-05-08 09:00（Asia/Shanghai）
- 执行状态：demo
- 可继续操作：
  - A. 详细分析指定今日简讯，例如：`A 1`。
  - B. 创建新的 thread，例如：`B 2 AI 搜索到浏览器入口`。
  - C. 调整简讯和 thread 的获取策略，例如：`C 少推没有来源的传闻`。
```
