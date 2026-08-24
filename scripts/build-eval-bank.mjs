import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const evalDir = path.join(root, "skrya", "evals");
const activePath = path.join(evalDir, "evals.json");
const bankPath = path.join(evalDir, "eval-bank.json");
const openClawContextPath = "skrya/evals/contexts/openclaw.json";

const active = JSON.parse(fs.readFileSync(activePath, "utf8"));

const journeyNames = {
  "01": "新的长期追踪请求",
  "02": "有直接自动化能力",
  "03": "没有直接自动化能力",
  "04": "一次性研究",
  "05": "扩展已有 topic",
  "06": "持续事件的时间线追踪",
  "07": "安装时选择数据位置",
  "08": "用户询问或修改数据位置",
  "09": "空日报诊断和补发不能串通道",
  "10": "确认主题后必须确认信源",
  "11": "试跑输出必须等同正式日报模板",
  "12": "agent 自主卸载 Skrya",
  "14": "自建简报模板创建与更新必须先提示并通过保存门禁",
};

const journeyTiers = {
  "journey-01": "llm-only",
  "journey-02": "runtime-required",
  "journey-03": "agent-context-required",
  "journey-04": "llm-only",
  "journey-05": "agent-context-required",
  "journey-06": "agent-context-required",
  "journey-07": "runtime-required",
  "journey-08": "runtime-required",
  "journey-09": "agent-context-required",
  "journey-10": "llm-only",
  "journey-11": "runtime-required",
  "journey-12": "runtime-required",
  "journey-14": "runtime-required",
};

const extras = [
  ["02", "1", "runtime-required", "用户确认 topic 后说：好的，每天早上 8 点推送。当前 agent 有自动化能力。请回应。", ["The response creates or updates an automation only after the user confirms the schedule.", "The automation prompt is a self-contained Skrya digest contract, not a vague reminder.", "The response keeps the test-run decision separate from automation creation.", "The response does not generate a digest before the user asks for a test run."]],
  ["02", "2", "runtime-required", "用户说：以后每天帮我跟踪 AI 浏览器动态，当前环境可以创建自动化。请按 Skrya 行为回应。", ["The response treats the request as recurring tracking.", "The response clarifies the durable topic scope before creating files.", "The response asks whether to create the daily digest task and what time it should run.", "The response does not collapse automation setup and test run into one implicit step."]],
  ["02", "3", "runtime-required", "用户已经确认 topic 和来源，现在要求创建每日 digest 任务。请给出正确行为。", ["The response creates an automation using the resolved topic id and data root.", "The automation contract includes delivery context and required topic files.", "The response updates delivery binding state when the host has channel context.", "The response asks separately whether to run a test digest now."]],
  ["02", "4", "runtime-required", "用户说：每天 8 点给我发国产大模型日报。当前 agent 有 automation tool。请回应。", ["The response first confirms the durable briefing intent.", "The response prepares a Skrya-specific recurring digest automation rather than a generic reminder.", "The response includes timestamped artifact and latest pointer requirements in the automation contract.", "The response does not claim the digest sources are connected before source confirmation."]],
  ["02", "5", "runtime-required", "用户确认信源计划后说：创建定时任务吧。请按 Skrya 行为回应。", ["The response creates or updates the recurring task only after source confirmation.", "The response uses the confirmed topic, data root, template fallback, and delivery binding.", "The response verifies the automation was created or reports the exact blocker.", "The response asks whether to run a separate test digest."]],

  ["03", "1", "agent-context-required", "用户说：以后每天帮我跟踪 AI 浏览器，当前环境不能创建自动化。请回应。", ["The response identifies that the environment cannot directly create automation.", "The response provides a copyable prompt for a more capable agent.", "The prompt is a self-contained Skrya digest contract.", "The response asks about a test run separately."]],
  ["03", "2", "agent-context-required", "用户确认 topic 后，agent 发现只有 user-mediated 自动化路径。请给出正确行为。", ["The response explains the user-mediated limitation.", "The response does not falsely claim automation has been created.", "The response provides a ready-to-send automation prompt.", "The response keeps source confirmation and test-run decisions explicit."]],
  ["03", "3", "agent-context-required", "用户说：持续跟踪具身智能融资。当前 host 没有自动化能力。请回应。", ["The response treats the request as recurring tracking.", "The response clarifies the topic scope and standards.", "The response states that no direct automation path is available.", "The response suggests a concrete prompt for a capable agent or host."]],
  ["03", "4", "agent-context-required", "用户说：每天给我推送 AI infra 新闻，但当前环境不能建任务。请按 Skrya 行为回应。", ["The response does not satisfy the request with a one-off news summary.", "The response explains the automation capability gap.", "The response gives a self-contained recurring digest prompt.", "The response asks whether the user wants a separate test run."]],
  ["03", "5", "agent-context-required", "用户问：你不能直接创建自动化时怎么办？请结合 Skrya 回答。", ["The response distinguishes user-mediated from non-automation environments.", "The response provides a copyable automation creation prompt.", "The response includes topic id, data root, delivery context, and template requirements.", "The response does not invent unavailable tools."]],

  ["05", "1", "agent-context-required", "用户说：把 AI 浏览器这个话题再加上模型 API 定价变化。已有 topic。请回应。", ["The response resolves which existing topic the user means.", "The response rewrites the request into stable brief.json preference language.", "The response asks for confirmation before writing changes.", "The response preserves existing automation plans."]],
  ["05", "2", "agent-context-required", "用户说：新能源汽车 topic 再加上充电桩政策。请按 Skrya 行为回应。", ["The response identifies the existing topic.", "The response translates the addition into durable brief preference language.", "The response confirms before updating topic state.", "The response does not discard existing source or automation configuration."]],
  ["05", "3", "agent-context-required", "用户确认扩展后，agent 应该更新 brief.json 并询问试跑。请给出正确行为。", ["The response updates brief.json with the confirmed expansion.", "The response preserves existing automation schedules.", "The response asks whether to run a test digest after the update.", "The response does not modify sources.json unless new sources are needed and confirmed."]],
  ["05", "4", "agent-context-required", "用户说：储能 topic 加上海外政策动态。已有 topic 和自动化。请回应。", ["The response resolves the existing topic.", "The response rewrites the added scope into stable preference language.", "The response asks for confirmation before writing files.", "The response keeps existing automation intact."]],
  ["05", "5", "agent-context-required", "用户说：在机器人 topic 里补充人形机器人赛道。请按 Skrya 行为回应。", ["The response identifies the correct existing topic.", "The response formulates the expansion in brief.json terms.", "The response asks for user confirmation before making changes.", "The response asks about a test run only after configuration handling."]],

  ["06", "3", "agent-context-required", "用户说：展开比亚迪闪充站这条线。请按时间线回放关键节点。", ["The response resolves the request against the existing thread.", "The response replays key nodes in timeline order.", "The response explains what to watch next.", "The response does not create a new top-level topic."]],
  ["06", "4", "agent-context-required", "日报命中比亚迪闪充站线时，agent 应该让用户感知到 callback。请给出正确行为。", ["The response includes the matching digest item number.", "The callback uses concrete facts and next watchpoints in 2-4 lines.", "The response does not use only a vague one-line progress note.", "The response keeps the update attached to the existing thread."]],
  ["06", "5", "agent-context-required", "用户说：以后这条线有新进展就接着往下讲。请按 Skrya 行为回应。", ["The response treats the request as a sub-topic thread, not a new topic.", "The response confirms the thread name and boundary.", "The response records or prepares a lightweight thread seed when needed.", "The response prioritizes future matching items for thread continuation."]],

  ["07", "1", "runtime-required", "用户安装 skill 时说：把 Skrya 装到 OpenClaw 里，数据放在这个挂载的 workspace 下面。请回应。", ["The response selects workspace-data-root for OpenClaw or mounted workspace environments.", "The response uses .skrya/data rather than the skill repository root.", "The response asks about migrating old topics or runs when present.", "The response tells the user where long-term config and history will be stored."]],
  ["07", "2", "runtime-required", "用户在普通桌面宿主安装 Skrya。请给出默认数据位置行为。", ["The response defaults to ~/.skrya for a normal desktop host.", "The response writes or confirms the corresponding data-root configuration.", "The response explains the durable memory location in natural language.", "The response does not store topic data in the skill code directory."]],
  ["07", "3", "runtime-required", "仓库里已有旧的 topics/ 和 runs/ 目录，用户同意迁移。请回应。", ["The response migrates missing topic and run data after confirmation.", "The response does not delete old data unless separately requested.", "The response reports the destination data root.", "The response avoids treating fixture data as user long-term data unless configured."]],
  ["07", "4", "runtime-required", "用户说：安装到 Codex，数据放 home 目录。请按 Skrya 行为回应。", ["The response selects home-data-root mode.", "The response configures the data root during setup.", "The response explains what will be stored there.", "The response does not require the user to manage raw JSON files."]],
  ["07", "5", "runtime-required", "安装完成后，agent 应该告诉用户长期记忆位置。请给出正确行为。", ["The response states the long-term memory location in user-readable language.", "The response names the stored categories such as topic config, digest history, and ingest state.", "The response does not only output internal debug paths.", "The response confirms whether migration was performed."]],

  ["08", "1", "runtime-required", "用户说：我的 topic 配置现在存在哪里？请回应。", ["The response reads the current data root.", "The response explains the current location in natural language.", "The response describes what data is stored there.", "The response does not ask the user for raw topic-id values."]],
  ["08", "2", "runtime-required", "用户说：帮我改到这个项目的 .skrya 下面。请回应。", ["The response explains the migration impact before proceeding.", "The response clarifies that old data will not be automatically deleted.", "The response asks for confirmation of target location and migration.", "The response does not silently move data."]],
  ["08", "3", "runtime-required", "用户确认迁移后，agent 应该运行 data-root 配置命令。请给出正确行为。", ["The response runs the data-root configuration after confirmation.", "The response migrates old topics and runs when requested.", "The response displays the new long-term memory location.", "The response does not delete old data without explicit request."]],
  ["08", "4", "runtime-required", "用户说：把数据位置改回 ~/.skrya。当前在 workspace 模式。请回应。", ["The response explains the effect of switching data roots.", "The response asks for confirmation before changing configuration.", "The response offers to migrate existing data.", "The response keeps old data unless deletion is explicitly requested."]],
  ["08", "5", "runtime-required", "用户询问数据位置但当前没有明确配置。请给出正确行为。", ["The response resolves the default based on the environment.", "The response explains the default in user-friendly terms.", "The response offers to configure a custom location if needed.", "The response does not invent a data root without checking."]],

  ["09", "1", "agent-context-required", "用户在韩国时政日报所在群里说：今天日报为什么没有内容？请回应。", ["The response finds the topic bound to the current channel.", "The response reads delivery-bindings.json for a current-channel match.", "The response distinguishes empty collection, empty generation, and empty delivery.", "The response does not scan all topics and resend unrelated digests."]],
  ["09", "2", "agent-context-required", "当前通道没有匹配的 delivery binding，用户问为什么日报是空的。请回应。", ["The response explains that the current channel has no explicit binding.", "The response asks which topic the user means.", "The response does not guess from global topics.", "The response does not resend all generated digests."]],
  ["09", "3", "agent-context-required", "生成内容存在但消息为空，用户要求补发。请给出正确行为。", ["The response resends only the digest bound to the current channel.", "The response uses an explicit message-sending path when the host supports it.", "The response verifies the message body is non-empty.", "The response does not use background announce as a substitute."]],
  ["09", "4", "agent-context-required", "同一通道绑定了两个 topic，用户要求补发。请回应。", ["The response asks which topic should be resent.", "The response does not concatenate both digests into one message.", "The response uses delivery bindings to enumerate only same-channel candidates.", "The response avoids cross-channel delivery by default."]],
  ["09", "5", "agent-context-required", "用户在 A 通道问 B 通道日报为什么是空的。请按 Skrya 行为回应。", ["The response does not deliver B-channel digests into A-channel by default.", "The response explains cross-channel delivery requires explicit support and request.", "The response checks the current channel binding first.", "The response does not scan all channels as a shortcut."]],

  ["11", "1", "runtime-required", "用户在 topic 配置完成后说：测试一轮。请回应。", ["The response outputs the test digest body directly without chatty preamble.", "The response uses the same template as a real daily digest.", "The response includes title, uniform line boxes, source references, separator, and ## 系统提示.", "The response does not save a formal artifact by default."]],
  ["11", "2", "runtime-required", "用户说：试跑一下新能源汽车简报。请按 Skrya 行为回应。", ["The response does not prepend status text before the digest body.", "The response renders with the configured digest template or default fallback.", "The ## 系统提示 explains follow-up operations.", "The response does not update latest-digest.md for an unsaved test run."]],
  ["11", "3", "runtime-required", "试跑输出没有命中足够条目。请给出正确行为。", ["The response still uses the formal digest template.", "The response explains the low hit count inside ## 系统提示 or digest judgment.", "The response does not wrap the body in template-free chatter.", "The response does not save the test output as a formal digest artifact."]],
  ["11", "4", "runtime-required", "用户明确要求保存试跑结果为正式 digest。请给出正确行为。", ["The response saves the output as a timestamped digest artifact only because the user asked.", "The response updates latest-digest.md as a pointer to the new artifact.", "The response reports the artifact filename.", "The response does not save test output silently."]],
  ["11", "5", "runtime-required", "试跑输出的 ## 系统提示 应该解释 dig: 2 指令。请给出正确行为。", ["The response explains that dig: 2 means deep analysis of item 2.", "The explanation is in user-readable Chinese.", "The section also mentions scan range and available follow-up operations.", "The section does not expose internal debug fields."]],

  ["12", "1", "runtime-required", "用户说：帮我卸载 Skrya。请回应。", ["The response explains the three uninstall modes before acting.", "The response asks the user to choose or confirm a mode.", "The response does not delete data from a vague uninstall request.", "The response describes which categories would be removed."]],
  ["12", "2", "runtime-required", "用户选择 skills-keep-data 卸载模式。请给出正确行为。", ["The response removes the skill while preserving topic config and history.", "The response explains that reinstalling can reuse the original data root.", "The response reports that data was kept.", "The response does not delete Skrya data or unrelated skills."]],
  ["12", "3", "runtime-required", "用户选择 data-keep-skills 模式。请给出正确行为。", ["The response reads and shows the current data root before deletion.", "The response confirms the long-term data being cleared.", "The response preserves installed skills.", "The response does not delete fixture data unless it is the configured data root and confirmed."]],
  ["12", "4", "runtime-required", "用户选择 complete 模式。请给出正确行为。", ["The response confirms skill directory, data root, data-root config, and global routing note cleanup.", "The response removes only Skrya-related global instruction blocks.", "The response prefers SKRYA-ROUTING-NOTE markers when present.", "The response reports removed categories after execution."]],
  ["12", "5", "runtime-required", "全局 AGENTS.md 里有其他 agent 记忆和 Skrya routing note。卸载时应如何处理？", ["The response removes only the smallest clearly Skrya-related block.", "The response does not clear the whole global instruction file.", "The response preserves unrelated agent memory.", "The response reports whether global-instruction cleanup was performed."]],

  ["14", "1", "runtime-required", "用户说：调整这个 topic 的现有简报模板，把来源放到最后。请按 Skrya 行为回应。", ["The response classifies the operation as update.", "The response warns before drafting that the active-Thread event-timeline module is mandatory.", "The response reads the configured template only as the update drafting basis.", "The response keeps candidate drafting separate from the shared save gate."]],
  ["14", "2", "runtime-required", "候选简报模板没有事件线时间线更新模块。请给出保存前检查的正确行为。", ["The response rejects the candidate before save.", "The response identifies the missing active-Thread timeline contract.", "The response leaves the existing configured template untouched.", "The response revises and revalidates the candidate instead of claiming it was saved."]],
  ["14", "3", "runtime-required", "自建模板候选已经包含时间线模块、无新增最新状态、简讯、信源和系统提示。下一步怎么做？", ["The response validates the complete candidate before replacing the configured template.", "The response saves only after validation succeeds.", "The response reports that the pre-save check passed.", "The response offers a separate test-run preview after saving."]],
  ["14", "4", "runtime-required", "模板保存前检查失败，缺少无新增时的最新状态。请按 Skrya 行为处理。", ["The response identifies the missing latest-state field.", "The response does not overwrite the current configured template.", "The response revises the candidate and runs validation again.", "The response does not report the template as saved while validation is failing."]],
  ["14", "5", "runtime-required", "用户要求自建模板完全删除 Thread 模块。请按 Skrya 行为回应。", ["The response explains that omission of the active-Thread timeline contract is not a supported customization.", "The response allows style and wording changes to the mandatory module.", "The response does not save a candidate that fails the timeline contract.", "The response preserves the current configured template unless a valid candidate is produced."]],
  ["14", "6", "runtime-required", "用户说：为这个 topic 创建一份新的简报模板，当前没有自建模板。请按 Skrya 行为回应。", ["The response classifies the operation as create.", "The response does not read an existing topic-specific template as the drafting basis.", "The response drafts from the default digest contract and the user's requested layout.", "The response validates the completed candidate through the shared save gate before creating the target."]],
];

function expected(journey) {
  return `The answer follows Skrya user journey ${Number(journey)}: ${journeyNames[journey]}.`;
}

const evals = active.evals.map((item) => ({ ...item, tier: "llm-only" }));
for (const [journey, index, tier, prompt, assertions] of extras) {
  const context_ids = tier === "llm-only" ? undefined : ["openclaw-gateway-runtime"];
  evals.push({
    id: `journey-${journey}-${index}`,
    name: `旅程 ${Number(journey)}：${journeyNames[journey]} / 测试 ${index}`,
    prompt,
    expected_output: expected(journey),
    assertions,
    tier,
    ...(context_ids ? { context_ids } : {}),
  });
}

evals.sort((a, b) => a.id.localeCompare(b.id));

const bank = {
  skill_name: "skrya",
  tiers: {
    "llm-only": "Fair for a bare LLM with SKILL.md context and no host tools, files, channel state, or automation runtime.",
    "agent-context-required": "Requires an agent runtime context such as host capability awareness, channel/conversation binding, or reading existing topic state.",
    "runtime-required": "Requires real side effects such as creating automations, migrating files, rendering digest artifacts, or uninstalling data/skills.",
  },
  contexts: {
    "openclaw-gateway-runtime": openClawContextPath,
  },
  journey_tiers: journeyTiers,
  evals,
};

fs.writeFileSync(bankPath, `${JSON.stringify(bank, null, 2)}\n`);
console.log(`Wrote ${bankPath} with ${evals.length} evals`);
