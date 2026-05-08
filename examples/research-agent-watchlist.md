# Research Agent Watchlist Demo

Use this when a user wants durable monitoring, not a one-off answer.

## User Request

```text
持续跟踪 research agent 和深度研究产品的变化，每天给我一份摘要。
```

## Skrya Topic Shape

```yaml
topic: research-agent-watchlist
language: zh-CN
scope:
  include:
    - research agents
    - deep research products
    - browser/search agents that can gather, synthesize, and cite sources
    - pricing, enterprise controls, and source transparency changes
  exclude:
    - generic chatbot launches without research workflow changes
    - unsourced social rumors
source_policy:
  automatically_connectable:
    - official blogs with feeds
    - product changelogs
    - media feeds
  runtime_retrieval:
    - web_search
    - news_search
    - social_search
  not_auto_connectable_yet:
    - login-only dashboards
    - private communities
delivery:
  default: creating conversation or channel
  test_run: ask separately
```

## Why It Matters

The durable object is not a single answer. It is the topic contract: what to watch, where evidence may come from, how to deliver it, and how user feedback changes future briefings.
