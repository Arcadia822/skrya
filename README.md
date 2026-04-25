# Skrya

Skrya 是一个面向 agent 的多主题信息追踪与简报工作区。

它不是传统 RSS 阅读器，也不是固定后台服务。Skrya 的核心思路是：把用户的自然语言关注需求，沉淀成可持续运行的 topic 配置，再由 agent 负责抓取、筛选、排序、生成日报和继续深挖。

## 它解决什么问题

很多人不是缺信息源，而是缺一个稳定的判断层：

- 我到底要持续关注什么？
- 今天这么多碎片里，哪些是真正值得看的事件？
- 哪些内容只是重复转述、榜单、轻量讨论？
- 如果某条值得深挖，它的来龙去脉、可信度和后续观察点是什么？

Skrya 把这些工作拆成一套 agent-native workflow：用户只说人话，agent 负责把它翻译成长期可维护的 topic、source、digest 和 deep-analysis。

## 适合的使用场景

- 每天追踪某家公司、行业、产品类别或市场主题
- 给非技术用户提供“每日重要事件”简报
- 把一次性反馈沉淀成长期偏好，比如“这类以后少推”
- 对日报中的某一条继续做事件分析
- 在不同 agent 环境里复用同一套 topic 配置
- 使用不稳定的第三方检索 skill，但不把项目绑定到这些 skill 上

## 非技术用户怎么用

用户不需要知道 topic id、RSS、JSON、skill 名称或检索工具细节。

可以直接这样说：

```text
以后每天帮我关注 AI 浏览器有什么重要动态
```

```text
我想持续看韩国娱乐圈这周真正值得跟的事件
```

```text
这条以后少推，类似的轻量榜单不用放日报里
```

```text
展开第 3 条，帮我判断这件事后面还值不值得看
```

agent 应该先确认用户真正想长期追踪的内容，再讨论是否创建每日自动简报，最后再问是否要试跑一次。

## 核心能力

Skrya 当前包含五个 bundled skills：

| Skill | 作用 |
| --- | --- |
| `topic-curation` | 把模糊关注需求整理成长期 topic，或调整现有 topic |
| `request-curation` | 把“多推/少推/别推”这类反馈写成稳定偏好 |
| `source-curation` | 管理可自动接入的信息渠道和检索能力 |
| `digest` | 生成编号清晰、可继续追问的主题日报 |
| `deep-analysis` | 对某个事件继续做脉络、可信度和后续观察分析 |

根 `skrya` skill 负责把用户请求路由到正确 workflow。

## Topic 模型

每个 topic 是一个独立目录：

```text
topics/<topic-id>/
  topic.json
  brief.json
  sources.json
  digest.md
  deep-analysis.md
```

其中：

- `topic.json` 保存主题身份和显示信息
- `brief.json` 保存用户真正关心什么
- `sources.json` 保存可自动接入的信息渠道
- `digest.md` 保存日报排序和排除标准
- `deep-analysis.md` 保存深度分析判断标准

正常用户不需要看到这些文件名；它们是 agent 内部执行细节。

## 外部检索接口

Skrya 支持使用第三方检索 skill，例如用户临时提供的 `agent-reach`。但 Skrya 不会把这些 skill 写成长期依赖。

长期配置只记录能力：

- `web_search`
- `news_search`
- `site_search`
- `social_search`
- `document_fetch`

运行时流程是：

1. Skrya 生成 provider-neutral 的 `skrya.retrieval-request.v1`
2. 当前 agent 选择可用检索工具执行
3. agent 把结果归一化为 `skrya.ingest.v1`
4. Skrya 只消费归一化 ingest，不直接消费第三方工具原始输出

运行产物写入：

```text
runs/<topic-id>/ingest/
  latest-ingest.json
  raw/
  normalized/
```

这样即使某个检索 skill 消失或换名，topic 配置仍然有效。

## 安装

### 方式一：直接克隆到 Codex skills 目录

```powershell
git clone https://github.com/arcadia822/skrya.git $HOME/.codex/skills/skrya
cd $HOME/.codex/skills/skrya
python -m pip install -e .
python -m skrya_orchestrator.main build-skill-pack --root . --host codex
```

仓库里已经包含生成后的 `SKILL.md` 和 `agents/openai.yaml`，克隆后即可被支持 skill 的 agent 发现。

### 方式二：克隆到任意目录后全局安装

```powershell
git clone https://github.com/arcadia822/skrya.git D:\work\skrya
cd D:\work\skrya
python -m pip install -e .
python -m skrya_orchestrator.main install-skill-pack --root . --host codex
```

也可以用便捷脚本：

```powershell
./setup.ps1 --host codex
```

Unix-like shell：

```bash
./setup --host codex
```

`install-skill-pack` 会优先使用 symlink 安装；如果系统不支持 symlink，会退回到复制安装。

## 常用命令

生成日报：

```powershell
python -m skrya_orchestrator.main digest --topic k-entertainment --root .
```

生成 provider-neutral 检索请求：

```powershell
python -m skrya_orchestrator.main retrieval-request --topic k-entertainment --root .
```

记录第三方检索工具归一化后的输出：

```powershell
python -m skrya_orchestrator.main ingest --topic k-entertainment --root . --file runs/k-entertainment/ingest/input.json
```

继续分析某条日报事件：

```powershell
python -m skrya_orchestrator.main deep-analysis --topic k-entertainment --event-number 3 --root .
```

重建 skill pack：

```powershell
python -m skrya_orchestrator.main build-skill-pack --root . --host all
```

## 项目结构

```text
.
  skill-pack.json             # 根 skill 元数据
  SKILL.md.tmpl               # 根 skill 模板
  SKILL.md                    # 生成后的根 skill
  agents/openai.yaml          # 生成后的 OpenAI metadata

  topic-curation/             # bundled skill
  request-curation/           # bundled skill
  source-curation/            # bundled skill
  digest/                     # bundled skill
  deep-analysis/              # bundled skill

  prompt-templates/           # host prompt pack 源模板
  topics/                     # 长期 topic 配置
  runs/                       # 运行产物，忽略提交
  src/skrya_orchestrator/     # CLI、构建、安装、digest 和 ingest 实现
  tests/                      # 单元测试和契约测试
```

## Source of Truth

如果你要改 agent-facing 行为，请改源模板，不要手改生成物：

1. 根 skill：改 `skill-pack.json` 和 `SKILL.md.tmpl`
2. 子 skill：改 `<skill>/skill.json` 和 `<skill>/SKILL.md.tmpl`
3. host prompt：改 `prompt-templates/`
4. 运行：

```powershell
python -m skrya_orchestrator.main build-skill-pack --root . --host all
```

`.skrya/hosts/`、`runs/`、`tmp/`、`__pycache__/`、`*.egg-info/` 都是运行或缓存产物，不是 source of truth。

## 开发与测试

安装本地包：

```powershell
python -m pip install -e .
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

当前测试覆盖：

- skill pack 生成和安装
- topic 名称解析
- digest 排序与输出格式
- deep-analysis 编号解析和来源隐藏
- runtime retrieval / ingest 接口
- skill 文档契约

## 设计文档

推荐先读：

- [current-system-design.md](design/current-system-design.md)
- [core-skills-spec.md](design/core-skills-spec.md)
- [external-retrieval-interface.md](docs/external-retrieval-interface.md)
- [user-journeys.md](docs/user-journeys.md)

## 贡献

欢迎提交 issue 和 PR。建议遵守以下原则：

- 先描述用户场景，再改配置或代码
- 新行为先补测试，尤其是 skill 契约测试
- 改 skill 文案时先改模板，再运行 `build-skill-pack`
- 不要把第三方检索 skill 写成 durable dependency
- 不要把来源列表、request id、文件名等内部细节暴露给普通用户

## License

当前仓库尚未包含开源许可证文件。正式公开发布前建议补充 `LICENSE`，例如 MIT、Apache-2.0 或其他与你的发布目标匹配的许可证。
