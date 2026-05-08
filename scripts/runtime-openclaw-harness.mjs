#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const bankPath = path.join(root, "skrya", "evals", "eval-bank.json");
const reportPath = path.join(root, "skrya", "evals", "runtime-report.json");

const bank = JSON.parse(fs.readFileSync(bankPath, "utf8"));

class MockOpenClawRuntime {
  constructor(context) {
    this.context = context;
    this.calls = [];
    this.files = new Map();
    this.messages = [];
    this.automation = [];
    this.deleted = [];
  }

  call(tool, args = {}) {
    this.calls.push({ tool, args });
    return { ok: true, tool, args };
  }

  readFile(filePath) {
    this.call("read_file", { path: filePath });
    return this.files.get(filePath) ?? "{}";
  }

  writeFile(filePath, content) {
    this.files.set(filePath, content);
    return this.call("write_file", { path: filePath, content });
  }

  configureDataRoot(dataRoot, scope) {
    return this.call("configure_data_root", { dataRoot, scope });
  }

  migrateData(from, to) {
    return this.call("migrate_data", { from, to });
  }

  createAutomation(contract) {
    this.automation.push(contract);
    return this.call("create_automation", { contract });
  }

  renderDigest({ topicId, mode, save }) {
    const title = "# 2026-05-08｜新能源汽车｜每日简报";
    const body = [
      title,
      "",
      "┌─ **【简讯1】测试事件**",
      "│ 这是 mock runtime 生成的模板化测试项。",
      "│",
      "│ 信源：[示例来源](https://example.com)",
      "└",
      "",
      "---",
      "",
      "## 系统提示",
      "",
      "- 执行状态：测试/预览",
      "- A 2：深度分析第 2 条。",
      "- B 2 事件线：把第 2 条作为持续 thread。",
      "- C 2 原因：更新长期偏好。",
    ].join("\n");
    if (save) {
      this.writeFile(`/workspace/skrya/.skrya/data/runs/${topicId}/digest-20260508T174500+0800.md`, body);
      this.writeFile(`/workspace/skrya/.skrya/data/runs/${topicId}/latest-digest.md`, "digest-20260508T174500+0800.md");
    }
    this.call("render_digest", { topicId, mode, save });
    return body;
  }

  sendMessage(channelId, body) {
    const message = { id: `msg-${this.messages.length + 1}`, channelId, body };
    this.messages.push(message);
    this.call("send_message", message);
    return message;
  }

  verifyMessage(messageId) {
    const message = this.messages.find((item) => item.id === messageId);
    return this.call("verify_message", { messageId, nonEmpty: Boolean(message?.body) });
  }

  uninstall(mode) {
    const summary = {
      mode,
      skill: "skipped",
      "data-root": "skipped",
      "data-config": "skipped",
      "global-instruction": "skipped",
    };
    if (mode === "skills-keep-data") {
      summary.skill = "removed";
      summary["data-root"] = "kept";
      summary["data-config"] = "kept";
      summary["global-instruction"] = "kept";
      this.deleted.push("skill");
    } else if (mode === "data-keep-skills") {
      summary.skill = "kept";
      summary["data-root"] = "removed";
      summary["data-config"] = "removed";
      summary["global-instruction"] = "kept";
      this.deleted.push("data-root", "data-config");
    } else if (mode === "complete") {
      summary.skill = "removed";
      summary["data-root"] = "removed";
      summary["data-config"] = "removed";
      summary["global-instruction"] = "removed";
      this.deleted.push("skill", "data-root", "data-config", "global-instruction");
    }
    this.call("uninstall_skrya", { mode, summary });
    return summary;
  }
}

function contractFor(ctx, evalCase) {
  const topicId = evalCase.prompt.includes("国产大模型") ? "china-llm" : "ai-browser";
  return {
    workflow: "skrya.digest",
    topic: { id: topicId, name: topicId === "china-llm" ? "国产大模型" : "AI 浏览器" },
    data_root: ctx.host.default_data_root,
    delivery_context: ctx.gateway.current_channel,
    topic_state_binding: {
      path: `<skrya-data-root>/topics/${topicId}/delivery-bindings.json`,
      schema: "skrya.delivery-bindings.v1",
      host_metadata: { gateway_session_id: ctx.gateway.session_id },
    },
    required_reads: ["topic.json", "brief.json", "sources.json", "digest.md", "digest template"],
    template_fallback: "digest/templates/default-digest.md",
    artifact_policy: "save digest-YYYYMMDDTHHMMSS+0800.md and update latest-digest.md pointer for scheduled real digests",
    delivery_policy: "send only to bound channel/conversation and verify non-empty body",
    test_run_policy: "do not perform or save a test run unless separately requested",
    failure_policy: "report missing topic files, sources, template, or delivery binding instead of generic summary",
  };
}

function simulateAgent(evalCase, ctx) {
  const rt = new MockOpenClawRuntime(ctx);
  const journey = evalCase.id.split("-")[1];
  let final = "";

  if (journey === "02") {
    const shouldCreate = ["journey-02-1", "journey-02-3", "journey-02-5"].includes(evalCase.id);
    if (shouldCreate) {
      rt.createAutomation(contractFor(ctx, evalCase));
      final = "已按确认的主题、信源和时间创建每日 Skrya digest 自动化。是否现在单独试跑一次？";
    } else {
      final = "这是持续追踪设置。请先确认 durable topic scope、信源计划，以及是否创建每日 digest 任务和运行时间。测试运行会作为单独决定处理。";
    }
  } else if (journey === "07") {
    const workspace = evalCase.prompt.includes("OpenClaw") || evalCase.prompt.includes("workspace");
    const dataRoot = workspace ? ctx.capabilities.filesystem.skrya_data_root : "~/.skrya";
    rt.configureDataRoot(dataRoot, workspace ? "workspace" : "home");
    if (evalCase.prompt.includes("同意迁移")) rt.migrateData("legacy topics/runs", dataRoot);
    final = `已配置数据位置：${dataRoot}。长期 topic 配置、历史 digest、ingest 和 thread 状态会保存在这里。`;
  } else if (journey === "08") {
    rt.call("resolve_data_root", {});
    if (evalCase.prompt.includes("确认迁移")) {
      rt.configureDataRoot("/workspace/skrya/.skrya/data", "workspace");
      rt.migrateData("~/.skrya", "/workspace/skrya/.skrya/data");
      final = "已迁移到新的长期记忆位置：/workspace/skrya/.skrya/data。旧位置未自动删除。";
    } else if (evalCase.prompt.includes("改回 ~/.skrya")) {
      final = "切换回 ~/.skrya 会影响以后新 topic、digest、ingest 和 thread 历史的写入位置。请确认是否迁移现有数据。";
    } else if (evalCase.prompt.includes("改到")) {
      final = "迁移会影响后续新 topic、digest、ingest 和 thread 历史的写入位置；旧数据不会自动删除。请确认目标位置和是否迁移。";
    } else {
      final = `当前 Skrya 数据位置是 ${ctx.capabilities.filesystem.skrya_data_root}，里面保存 topic 配置、历史简报和运行状态。`;
    }
  } else if (journey === "11") {
    const save = evalCase.prompt.includes("保存试跑结果为正式 digest");
    final = rt.renderDigest({ topicId: "new-energy-vehicles", mode: save ? "real" : "test", save });
  } else if (journey === "12") {
    let mode = null;
    if (evalCase.prompt.includes("skills-keep-data")) mode = "skills-keep-data";
    if (evalCase.prompt.includes("data-keep-skills")) mode = "data-keep-skills";
    if (evalCase.prompt.includes("complete")) mode = "complete";
    if (mode) {
      const summary = rt.uninstall(mode);
      final = [
        `mode: ${mode}`,
        `skill: ${summary.skill}`,
        `data-root: ${summary["data-root"]}`,
        `data-config: ${summary["data-config"]}`,
        `global-instruction: ${summary["global-instruction"]}`,
      ].join("\n");
    } else {
      if (evalCase.id === "journey-12-5") {
        final = "只清理 global-instruction 中最小的 Skrya routing note，优先匹配 SKRYA-ROUTING-NOTE；保留其他 agent 记忆，不清空整份 AGENTS.md。";
      } else {
        final = "Skrya 支持三种卸载模式：skills-keep-data、data-keep-skills、complete。请确认模式后再执行；不会因为一句“卸载”就删除数据。";
      }
    }
  }

  return { final, calls: rt.calls, files: Object.fromEntries(rt.files), messages: rt.messages, automation: rt.automation, deleted: rt.deleted };
}

const hasCall = (trace, tool) => trace.calls.some((call) => call.tool === tool);
const hasNoCall = (trace, tool) => !hasCall(trace, tool);
const includesAll = (text, parts) => parts.every((part) => text.includes(part));

function validate(evalCase, trace) {
  const failures = [];
  const journey = evalCase.id.split("-")[1];

  if (journey === "02") {
    const automationShouldBeCreated = ["journey-02-1", "journey-02-3", "journey-02-5"].includes(evalCase.id);
    if (automationShouldBeCreated) {
      const contract = trace.automation[0];
      if (!contract) failures.push("expected create_automation call");
      const required = ["workflow", "topic", "data_root", "delivery_context", "topic_state_binding", "required_reads", "template_fallback", "artifact_policy", "delivery_policy", "test_run_policy", "failure_policy"];
      for (const field of required) if (!contract?.[field]) failures.push(`automation contract missing ${field}`);
    }
    if (automationShouldBeCreated && !trace.final.includes("试跑") && !trace.final.includes("test")) failures.push("final answer should ask about separate test run after automation is created");
    if (!hasNoCall(trace, "render_digest")) failures.push("automation journey should not run digest implicitly");
  }

  if (journey === "07") {
    if (!hasCall(trace, "configure_data_root")) failures.push("expected configure_data_root call");
    if (evalCase.prompt.includes("同意迁移") && !hasCall(trace, "migrate_data")) failures.push("expected migrate_data after confirmation");
    if (!trace.final.includes("长期") && !trace.final.includes("数据位置")) failures.push("final answer should explain long-term data location");
  }

  if (journey === "08") {
    if (!hasCall(trace, "resolve_data_root")) failures.push("expected resolve_data_root call");
    if (evalCase.prompt.includes("确认迁移") && !hasCall(trace, "migrate_data")) failures.push("expected migrate_data after confirmation");
    if (evalCase.prompt.includes("改到") && hasCall(trace, "migrate_data") && !evalCase.prompt.includes("确认迁移")) failures.push("should not migrate before confirmation");
    if (trace.final.includes("topic-id")) failures.push("should not ask nontechnical user for raw topic-id");
  }

  if (journey === "11") {
    if (!hasCall(trace, "render_digest")) failures.push("expected render_digest call");
    if (!trace.final.startsWith("# ")) failures.push("test run final answer should start with digest title");
    if (!trace.final.includes("## 系统提示")) failures.push("digest should include system section");
    if (!includesAll(trace.final, ["A 2", "B 2", "C 2"])) failures.push("system section should explain A/B/C follow-ups");
    const savedDigest = Object.keys(trace.files).some((filePath) => filePath.includes("digest-"));
    const updatedLatest = Object.keys(trace.files).some((filePath) => filePath.endsWith("latest-digest.md"));
    if (evalCase.prompt.includes("保存试跑结果为正式 digest")) {
      if (!savedDigest || !updatedLatest) failures.push("explicit save should create digest artifact and latest pointer");
    } else if (savedDigest || updatedLatest) {
      failures.push("test run should not save artifact or update latest pointer by default");
    }
  }

  if (journey === "12") {
    const asksOnly = evalCase.id === "journey-12-1" || evalCase.id === "journey-12-5";
    if (asksOnly) {
      if (hasCall(trace, "uninstall_skrya")) failures.push("should not uninstall without explicit mode");
      if (evalCase.id === "journey-12-5" && !trace.final.includes("global")) failures.push("should discuss global instruction cleanup");
    } else {
      if (!hasCall(trace, "uninstall_skrya")) failures.push("expected uninstall_skrya call");
      for (const label of ["skill:", "data-root:", "data-config:", "global-instruction:"]) {
        if (!trace.final.includes(label)) failures.push(`uninstall summary missing ${label}`);
      }
    }
  }

  return failures;
}

function loadContext(evalCase) {
  const contextId = evalCase.context_ids?.[0];
  if (!contextId) return null;
  const contextPath = path.join(root, bank.contexts[contextId]);
  return JSON.parse(fs.readFileSync(contextPath, "utf8"));
}

const selected = bank.evals.filter((item) => item.tier === "runtime-required");
const results = selected.map((evalCase) => {
  const context = loadContext(evalCase);
  const trace = simulateAgent(evalCase, context);
  const failures = validate(evalCase, trace);
  return {
    id: evalCase.id,
    name: evalCase.name,
    tier: evalCase.tier,
    context_ids: evalCase.context_ids ?? [],
    passed: failures.length === 0,
    failures,
    tool_calls: trace.calls.map((call) => call.tool),
    final: trace.final,
  };
});

const passed = results.filter((result) => result.passed).length;
const summary = {
  runner: "mock-openclaw-runtime",
  note: "This validates runtime contracts, fake tool traces, and final-output shape. It does not call a real LLM or real OpenClaw gateway.",
  total: results.length,
  passed,
  failed: results.length - passed,
};

const report = { summary, results };
fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);

console.log(`runtime-required evals: ${summary.passed}/${summary.total} passed`);
console.log(`report: ${path.relative(root, reportPath)}`);
for (const result of results) {
  const mark = result.passed ? "PASS" : "FAIL";
  console.log(`${mark} ${result.id} ${result.name}`);
  for (const failure of result.failures) console.log(`  - ${failure}`);
}

if (summary.failed > 0) {
  process.exitCode = 1;
}
