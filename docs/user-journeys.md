# 用户旅程

这些旅程定义了支持 Skrya 的 agent 面向普通用户时应该怎么行动。关键差异不是 agent 的产品名称，而是当前环境有没有创建自动化任务的能力。

## 能力模式

- `automation-capable`：agent 可以在用户确认后直接创建或更新自动化任务。
- `user-mediated`：agent 不能直接创建自动化任务，但可以给用户一段可复制给其他 agent 的提示词。
- `non-automation`：当前环境没有可用的自动化路径。

## 投递上下文模式

这些规则只适用于有 channel/conversation 概念的 agent。没有通道概念的 agent 不需要伪造通道，只按 topic、用户意图和可用自动化上下文处理。

- `same-channel`：默认模式。用户在哪个 channel/conversation 创建每日简报，后续定时推送、补发和空内容诊断都回到同一个 channel/conversation。
- `cross-channel-explicit`：只有用户明确指定另一个通道，且当前 host 明确支持跨通道发送时才使用。
- `cross-channel-avoided`：OpenClaw 这类架构默认避免跨通道投递；如果用户没有明确说明，不要猜测或转发到其他通道。

## 数据位置模式

- `home-data-root`：默认模式，topic 配置和运行历史保存在 `~/.skrya`。
- `workspace-data-root`：容器、OpenClaw 或挂载 workspace 环境使用，topic 配置和运行历史保存在当前 workspace 的 `.skrya/data`。
- `custom-data-root`：用户明确指定路径时使用；agent 应说明这是长期记忆位置，并在迁移前确认。

## 旅程 1：新的长期追踪请求

用户说：

```text
帮我收集 LLM 实时资讯
```

期望流程：

1. 先判断这是长期追踪，而不是一次性搜索。
2. 用自然语言澄清用户真正想看的信息类型。
3. 给出稳定的话题描述，并在写入配置前让用户确认。
4. 在输出任何日报前，先处理自动化问题。
5. 如果 agent 可以创建自动化，询问是否创建每日简报任务以及运行时间。
6. 如果 agent 不能直接创建自动化，给出一段可直接转发的自动化创建提示词。
7. 单独询问用户现在是否要试跑一次。
8. 只有用户明确同意后，才运行测试日报。

不应该：

- 直接搜索并把结果倾倒在聊天里
- 把“找来源”当成最终成果
- 把试跑决定藏在自动化提示词里
- 在用户确认试跑前生成 digest

## 旅程 2：有直接自动化能力

用户说：

```text
以后每天帮我跟踪 AI 浏览器的最新动态
```

期望流程：

1. 默认理解为持续追踪。
2. 澄清哪些动态值得进入简报。
3. 确认长期 topic 表述。
4. 询问是否创建每日 digest 任务，以及每天几点运行。
5. 自动化决定处理完以后，再询问是否现在试跑。
6. 只有用户明确同意后，才运行测试 digest。

## 旅程 3：没有直接自动化能力

用户说：

```text
以后每天帮我跟踪 AI 浏览器的最新动态
```

期望流程：

1. 默认理解为持续追踪。
2. 澄清哪些动态值得进入简报。
3. 确认长期 topic 表述。
4. 说明当前环境属于 `user-mediated` 还是 `non-automation`。
5. 如果不能直接创建自动化，给出一段可发送给更合适 agent 的提示词。
6. 单独询问是否现在试跑。
7. 只有用户明确同意后，才运行测试 digest。

## 旅程 4：一次性研究

用户说：

```text
现在帮我总结一下今天 LLM 圈最重要的三件事
```

期望流程：

1. 判断这是一次性研究，而不是长期追踪。
2. 直接回答，不强制创建 topic。
3. 可以顺带提示：如果用户希望每天追踪，Skrya 可以把它变成长期 topic。

## 旅程 5：扩展已有 topic

用户说：

```text
把 AI 浏览器这个话题再加上模型 API 定价变化
```

期望流程：

1. 先解析用户说的是哪个已有 topic。
2. 把请求改写成稳定的 `brief.json` 偏好语言。
3. 写入前确认这段表述。
4. 保留已有自动化计划。
5. 修改后再询问是否需要试跑一次。

## 旅程 6：持续事件的时间线追踪

用户说：

```text
新能源汽车这个 topic 里，帮我持续跟比亚迪闪充站这条线；以后有新进展就接着往下讲。
```

期望流程：

1. 先解析用户说的是哪个已有 topic，而不是把“比亚迪闪充站”误当成新的 topic。
2. 判断用户要的是一个小于 topic 的持续事件实体，而不是一次性 deep-analysis。
3. 用自然语言确认这条thread的名字和边界，例如“你想跟的是比亚迪闪充站从发布、落地到扩张的整条进展线”。
4. 如果当前运行时还没有这条线，先把这条线写成一个轻量 `thread` seed，再用最新 digest artifact 刷出运行时对象。
5. 以后只要出现新站点开通、覆盖城市扩张、合作方接入或真实体验反馈，优先续写到这条线，而不是每天重新开一个新事件。
6. 当日报命中这条线时，输出上要让用户感知到 callback，但不要只写一句笼统提示；应该用 2-4 行写清楚命中的简讯编号、具体事实推进和后续看点。
7. 如果用户说“展开这条线”，应该按时间线回放关键节点，并说明下一步还该观察什么。
8. 在日报结尾给出短反馈选项，让用户能用 `A 3 5 12`、`B 3 4 5 持续关注`、`C 6 7 我不喜欢，如果是 xxx 不要关注` 这类指令继续调教系统。

不应该：

- 把“比亚迪闪充站”直接升级成新的长期 topic
- 每天都把相关进展写成完全无关联的新 digest item
- 只分析最新一条新闻，忽略此前已经累积的上下文
- 把thread更新压缩成“今天又推进了一步”这类没有具体信息量的句子

## 旅程 7：安装时选择数据位置

用户安装 skill 时说：

```text
把 Skrya 装到 OpenClaw 里，数据放在这个挂载的 workspace 下面。
```

期望流程：

1. 判断宿主环境是否适合 `home-data-root` 还是 `workspace-data-root`。
2. 对普通桌面宿主默认使用 `~/.skrya`，对 OpenClaw、容器或明确要求挂载目录的环境默认使用 workspace `.skrya/data`。
3. 安装时写入对应配置，而不是让 topic 数据落在 skill 仓库根目录。
4. 如果仓库里已经有旧的 `topics/` 或 `runs/`，询问是否迁移；用户同意后复制缺失文件到新的 data root。
5. 安装结束时告诉用户“长期关注配置和历史简报会保存在 X”，不要只输出内部路径列表。

可用命令示例：

```bash
./setup --host openclaw --data-root-mode workspace --migrate-data
./setup --host codex --data-root-mode home --migrate-data
```

## 旅程 8：用户询问或修改数据位置

用户说：

```text
我的 topic 配置现在存在哪里？帮我改到这个项目的 .skrya 下面。
```

期望流程：

1. 先读取当前 data root，并用自然语言说明当前位置。
2. 解释迁移影响：以后新 topic、digest、ingest 和thread历史都会写到新位置；旧位置不会被自动删除。
3. 让用户确认目标位置和是否迁移旧数据。
4. 用户确认后运行 data-root 配置命令，并迁移旧的 `topics/` 和 `runs/`。
5. 修改后再显示新的长期记忆位置。

可用命令示例：

```bash
python3 -m skrya_orchestrator.main data-root --root . --set .skrya/data --scope workspace --migrate
python3 -m skrya_orchestrator.main data-root --root .
```

不应该：

- 要求普通用户理解 `topic-id` 或手动移动 JSON 文件
- 静默把数据写入 skill 仓库根目录
- 迁移后删除旧数据，除非用户单独明确要求

## 旅程 9：空日报诊断和补发不能串通道

这些规则只适用于 host 暴露 channel/conversation 的情况。没有通道概念的 agent 只需要按 topic 和可用自动化上下文排查。

用户在韩国时政日报所在群里说：

```text
@露娜 怎么今天日报没有内容？
```

期望流程：

1. 先按当前 channel/conversation 找到绑定到这个通道的定时 topic，而不是扫出今天所有生成过的 digest。
2. 检查该 topic 的生成状态和投递状态，区分“采集为空”“生成为空”“消息发送为空/未展开”。
3. 如果生成内容存在但消息为空，使用显式消息工具补发当前 channel 绑定的那一份，并在支持时校验消息体非空。
4. 如果同一 channel 绑定了多个 topic，先问用户要补发哪一个。
5. 不要把另一个 channel 创建的 topic 一起补发到当前 channel。

不应该：

- 因为两个 topic 都在 08:00 生成，就把它们拼成一条补发消息
- 把“军民融合”这种另一个通道的日报发到韩国时政通道
- 用后台 announce 成功代替显式消息发送和非空校验

## 旅程 10：确认主题后必须确认信源

用户说：

```text
使用 skrya，每天给我一份 BYD，以及新能源汽车，储能相关的简报。主要关注国内外主流媒体内容
```

agent 发现已有「新能源汽车」topic，建议扩展。用户回复：

```text
确认
```

期望流程：

1. 写入或准备写入 BYD、新能源汽车、储能的关注范围前，先确认这确实是扩展已有 topic，而不是新建多个 topic。
2. 用户确认主题范围和标准后，不要直接说“已接入”。
3. 先进入信源确认：提出国内外主流媒体、财经/产业媒体、英文媒体、官方/可回溯来源等候选信源组。
4. 如果当前环境配置了 X、微信公众号或其他信源渠道 skill，也要纳入候选信源计划，不能只列网页/新闻检索。
5. 对每组说明为什么适合这个 topic，并标注当前能否自动接入。
6. 让用户确认信源计划后，才更新长期 sources 配置并创建或更新每日任务。
7. 如果已有 topic 已经有足够信源，说明哪些已覆盖，哪些是 BYD/储能扩展后新增的信源缺口。
8. 每日任务创建或更新后，主动询问用户是否现在试跑一轮。

不应该：

- 用户确认主题范围后立刻宣布“已接入”
- 只写“国内外主流媒体优先”但不列出候选信源
- 环境里有 X / 微信公众号检索能力，却完全不纳入信源选择
- 在用户确认信源前写入 `sources.json`
- 在没有确认信源计划前创建或更新每日自动化
- 创建成功后不主动询问是否试跑

## 旅程 11：试跑输出必须等同正式日报模板

用户在 topic 配置完成后说：

```text
测试一轮
```

期望流程：

1. 直接输出测试简报正文，不要先发一段“我跑一轮测试”的闲聊。
2. 使用正式日报同一套模板：标题、统一 line box、每条信源、`---`、`## 系统提示`。
3. `## 系统提示` 里说明这是测试/预览、扫描时间范围、后续可用操作，并解释 `A 2` 这类指令是什么意思。
4. 测试结果默认不保存为 latest digest，也不要在用户可见输出里说“已写入测试产物”。
5. 如果测试输出没有命中足够条目，可以在 `## 系统提示` 或 digest 判断中说明，不要用模板外废话包裹正文。

不应该：

- 在正文前输出“蛋糕实验开始”这类状态句
- 结尾缺少 `## 系统提示`
- 只说“可以回复 A 2”，但不解释 A/B/C 的含义
- 把测试产物写入或宣称写入 `latest-digest.md`

## 旅程 12：agent 自主卸载 Skrya

用户说：

```text
帮我卸载 Skrya。
```

期望流程：

1. 先说明 Skrya 支持三种卸载模式，并让用户选择或确认：
   - `skills-keep-data`：卸载技能，保留 topic 配置、历史 digest、ingest 和 thread 数据。
   - `data-keep-skills`：清空 Skrya 配置和数据，保留已安装技能。
   - `complete`：完全卸载，删除技能、Skrya 数据/config，并移除全局指令记忆里的 Skrya 路由说明。
2. 对 `skills-keep-data`，说明以后重新安装 Skrya 后仍可继续使用原 data root。
3. 对 `data-keep-skills`，先读取并展示当前 data root，确认要删除的是哪一份长期配置/历史数据。
4. 对 `complete`，同时确认技能目录、data root、data-root config，以及全局 `AGENTS.md` / `CLAUDE.md` / `TOOLS.md` / `tools.md` 或 documented global memory 里的 Skrya routing note 都会被清理。
5. 只移除 Skrya 相关的全局指令块。优先删除带 `SKRYA-ROUTING-NOTE` 标记的块；如果没有标记，只删除明确属于 Skrya 的最小段落，不要清空整份全局指令文件。
6. 执行后汇报删除了哪些类别：skill、data-root、data-config、global-instruction。

可用命令示例：

```bash
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode skills-keep-data
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode data-keep-skills
python3 -m skrya_orchestrator.main uninstall-skill-pack --root . --host auto --mode complete
```

不应该：

- 用户只说“卸载”就直接删除数据
- 清空整份全局 `AGENTS.md`
- 把当前 workspace 的示例 fixture 当成用户长期数据删除，除非 data root 明确指向这里且用户确认
- 删除非 Skrya 技能或其他 agent 的记忆
