<div align="center">

# Skrya

**Turn "keep me updated on this" into a durable AI briefing workflow.**

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
![Skrya](https://img.shields.io/badge/skrya-v0.1.0-0ea5e9.svg)

[Chinese](README.md) · **English**

</div>

Skrya is a briefing skill pack for AI agents. The user describes what they want to track; the agent turns that into a durable topic with confirmed scope, confirmed sources, recurring delivery, daily digests, follow-up analysis, and long-term feedback memory.

## Quick Start

Send this to your agent:

```text
Install Skrya from https://github.com/Arcadia822/skrya. After installation, send me a daily briefing about important AI browser developments.
```

The agent should read the repository installation instructions and handle the setup. You should not need to copy shell commands manually. After installation, it should clarify what you actually want, then confirm sources and delivery. It should not dump search results immediately. We are all grateful for this restraint.

## Core Value

### Daily Briefings

Turn a standing area of interest into a reusable daily briefing. Each item has source references, judgment, and follow-up actions.

### Source Discipline

Skrya confirms sources before declaring a topic ready. It distinguishes automatically connected sources, runtime retrieval sources, and sources that cannot be connected yet.

### Skill Composition

Skrya looks for useful local skills and uses them to widen source coverage. For example, it can work with `agent-reach` for public web and social retrieval, or `wechat-article-search` for WeChat Official Account articles. Skrya does not focus on bypassing login walls or access restrictions; it organizes available sources into reusable briefing workflows.

### Continuing Threads

The same developing story should not become unrelated headlines every day. Skrya links related items into a continuing thread so the context stays visible.

### Feedback Becomes Memory

When you say "show fewer items like this", "keep tracking this", or "expand item 3", Skrya turns that into durable preferences instead of treating it as disposable chat.

### Channel Isolation

In hosts with channels or conversations, a briefing created in one channel stays bound to that channel by default. Resends and empty-briefing diagnosis do not pull in another channel's topic.

## Language

Skrya does not need an install-time language setting. Language belongs to the topic:

- New topics default to the language used when the topic is created.
- You can explicitly ask for a topic to output in Chinese or English.
- The project currently supports Chinese and English output.
- If you give feedback in another language later, the agent should answer in your feedback language without changing the topic's briefing language unless you ask.

## Privacy

Skrya runs fully locally. It has no telemetry, cloud sync, or hosted backend, and it does not proactively upload your topic config, briefing history, feedback preferences, or local data. Other networked skills you ask the agent to combine with Skrya, such as web retrieval, browser tools, or WeChat article search, follow their own external-access rules.

## Uninstall

Skrya supports three uninstall modes:

| Mode | Removes | Keeps |
| --- | --- | --- |
| `skills-keep-data` | Installed skills | Topic config, history, data-root config |
| `data-keep-skills` | Skrya data and data-root config | Installed skills |
| `complete` | Skills, data, and Skrya routing notes in global instructions | Unrelated user instructions |

Tell your agent:

```text
Uninstall Skrya. First explain the three uninstall modes, then wait for my confirmation before acting.
```

Complete uninstall removes only marked Skrya instruction blocks such as `SKRYA-ROUTING-NOTE`. It should not wipe unrelated `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, or `tools.md` content.

## More Docs

| Doc | Covers |
| --- | --- |
| [Install](INSTALL.md) | Agent-facing install, uninstall, and upgrade steps |
| [User journeys](docs/user-journeys.md) | How agents should behave for nontechnical users |
| [Threads](docs/threads.md) | Continuing event timelines |
| [External retrieval](docs/external-retrieval-interface.md) | Runtime retrieval normalization |
| [Domain model](docs/domain-model.md) | Topic, request, source, thread, channel, and related entities |
| [Contributing](CONTRIBUTING.md) | Development, tests, code layout, and technical design |

## License

[MIT](LICENSE)
