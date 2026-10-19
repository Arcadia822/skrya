import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    

    def test_install_doc_contains_agent_facing_operations(self) -> None:
        content = (ROOT / "INSTALL.md").read_text(encoding="utf-8")

        self.assertIn("install-skill-pack", content)
        self.assertIn("data-root --root", content)
        self.assertIn("uninstall-skill-pack", content)
        self.assertIn("skills-keep-data", content)
        self.assertIn("data-keep-skills", content)
        self.assertIn("complete", content)
        self.assertIn("version --root . --check-latest", content)
        self.assertIn("upgrade --root . --migrate-thread-naming", content)
        self.assertIn("build-skill-pack --root . --host all", content)
        self.assertIn("docs/upgrade.md", content)

    def test_english_readme_is_available_from_homepage(self) -> None:
        zh_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        en_readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("**简体中文** · [English](README.md)", zh_readme)
        self.assertIn("[简体中文](README.zh-CN.md) · **English**", en_readme)
        self.assertIn('<div align="center">', en_readme)
        self.assertEqual(2, en_readme.count("img.shields.io"))
        self.assertIn("Turn \"keep me updated on this\"", en_readme)
        self.assertIn("## Quick Start", en_readme)
        self.assertIn("## Core Value", en_readme)
        self.assertIn("Daily Briefings", en_readme)
        self.assertIn("Source Discipline", en_readme)
        self.assertIn("Skill Composition", en_readme)
        self.assertIn("agent-reach", en_readme)
        self.assertIn("wechat-article-search", en_readme)
        self.assertIn("bypassing login walls", en_readme)
        self.assertIn("Continuing Threads", en_readme)
        self.assertIn("Channel Isolation", en_readme)
        self.assertIn("Delivery bindings", en_readme)
        self.assertIn("## Privacy", en_readme)
        self.assertIn("runs fully locally", en_readme)
        self.assertIn("does not proactively upload", en_readme)
        self.assertNotIn("## Where Data Lives", en_readme)
        self.assertIn("## Uninstall", en_readme)
        self.assertIn("INSTALL.md", en_readme)
        self.assertIn("## What You Get", en_readme)
        self.assertIn("examples/ai-browser-daily-briefing.md", en_readme)
        self.assertIn("git clone https://github.com/Arcadia822/skrya.git", en_readme)
        self.assertIn("./setup --host auto", en_readme)
        self.assertNotIn("## Digest Example", en_readme)
        for command_detail in [
            "install-skill-pack",
            "uninstall-skill-pack",
            "git pull",
            "upgrade --root",
            "data-root --root",
        ]:
            self.assertNotIn(command_detail, en_readme)
        en_without_language_link = en_readme.replace("[简体中文](README.zh-CN.md) · **English**", "")
        self.assertNotRegex(en_without_language_link, r"[\u4e00-\u9fff]")

    def test_new_energy_vehicles_topic_fixture_models_thread_journey(self) -> None:
        topic_dir = ROOT / "tests" / "fixtures" / "topics" / "new-energy-vehicles"

        topic = json.loads((topic_dir / "topic.json").read_text(encoding="utf-8"))
        brief = json.loads((topic_dir / "brief.json").read_text(encoding="utf-8"))
        sources = json.loads((topic_dir / "sources.json").read_text(encoding="utf-8"))
        sample_events = json.loads((topic_dir / "sample-events.json").read_text(encoding="utf-8"))
        seeds = json.loads((topic_dir / "thread-seeds.json").read_text(encoding="utf-8"))

        self.assertEqual("new-energy-vehicles", topic["topic"])
        self.assertEqual("新能源汽车", topic["name"])
        self.assertIn("持续发酵的大事件", brief["requests"][2]["content"])
        self.assertEqual("runtime-retrieval", sources["sources"][0]["type"])
        self.assertIn("比亚迪闪充站", sample_events[0]["title"])
        self.assertEqual("比亚迪闪充站", seeds["threads"][0]["name"])
        self.assertIn("比亚迪兆瓦闪充站", seeds["threads"][0]["match_terms"])



    def test_uninstall_journey_and_skill_contract_are_documented(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        for phrase in [
            "skills-keep-data",
            "data-keep-skills",
            "complete",
            "AGENTS.md",
            "SKRYA-ROUTING-NOTE",
        ]:
            self.assertIn(phrase, root_skill)
            self.assertIn(phrase, journeys)
            self.assertIn(phrase, readme)

        self.assertIn("旅程 12：agent 自主卸载 Skrya", journeys)
        self.assertIn("不要清空整份全局指令文件", journeys)
        self.assertIn("skill", root_skill)
        self.assertIn("data-root", root_skill)
        self.assertIn("data-config", root_skill)
        self.assertIn("global-instruction", root_skill)
        self.assertIn("fixed four-category summary", root_skill)
        self.assertIn("用一句“已完成”代替四类执行结果汇总", journeys)

    def test_agents_routes_unconfigured_topic_info_requests_to_topic_curation(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("important information", content)
        self.assertIn("without first naming an existing configured `topic-id`", content)
        self.assertIn("route to `topic-curation` first instead of answering directly", content)
        self.assertIn("clarify the user's crawling or tracking request", content)
        self.assertIn("company, industry, market, product category, or theme", content)

    def test_root_and_bundled_skill_docs_exist(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").exists(), "root umbrella skill should exist")
        self.assertTrue((ROOT / "README.md").exists(), "English README should exist")
        self.assertTrue((ROOT / "README.zh-CN.md").exists(), "Chinese README should exist")
        self.assertTrue((ROOT / "INSTALL.md").exists(), "agent-facing install guide should exist")
        self.assertTrue((ROOT / "skrya" / "SKILL.md").exists(), "installer-facing skrya skill should exist")
        self.assertTrue((ROOT / "topic-curation" / "SKILL.md").exists(), "topic-curation skill should exist")
        self.assertTrue((ROOT / "request-curation" / "SKILL.md").exists(), "request-curation skill should exist")
        self.assertTrue((ROOT / "source-curation" / "SKILL.md").exists(), "source-curation skill should exist")
        self.assertTrue((ROOT / "digest" / "SKILL.md").exists(), "digest skill should exist")
        self.assertTrue((ROOT / "deep-analysis" / "SKILL.md").exists(), "deep-analysis skill should exist")
        self.assertTrue((ROOT / "CONTRIBUTING.md").exists(), "contribution guide should exist")
        self.assertTrue((ROOT / "LICENSE").exists(), "license should exist")

    def test_license_and_contributing_are_documented(self) -> None:
        readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("CONTRIBUTING.md", readme)
        self.assertIn("MIT", readme)
        self.assertIn("build-skill-pack", contributing)
        self.assertIn("Use `thread`, not `event-thread`", contributing)
        self.assertIn("## Architecture", contributing)
        self.assertIn("## Runtime Data", contributing)
        self.assertIn("~/.skrya", contributing)
        self.assertIn(".skrya/data", contributing)
        self.assertIn("<skrya-data-root>/topics/<topic-id>/", contributing)
        self.assertIn("## Code Layout", contributing)
        self.assertIn("## Technical Design Notes", contributing)
        self.assertIn("MIT License", license_text)
        self.assertIn('license = "MIT"', pyproject)

    def test_root_metadata_allows_implicit_invocation(self) -> None:
        content = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: skrya', content)
        self.assertIn("allow_implicit_invocation: true", content)

    def test_root_default_prompt_is_friendly_for_nontechnical_users(self) -> None:
        content = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("告诉我你想持续关注什么", content)
        self.assertNotIn("Use $skrya", content)

    def test_skills_hide_internal_identifiers_and_source_jargon_from_users(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        source_curation = (ROOT / "source-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Do not ask nontechnical users for raw `topic-id` values", root_skill)
        self.assertIn("resolve an internal `topic-id` before reading or writing files", topic_curation)
        self.assertIn("自动接入", source_curation)
        self.assertIn("Do not expose RSS as a user-facing requirement", source_curation)

    

    def test_skills_describe_provider_neutral_runtime_retrieval(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        source_curation = (ROOT / "source-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("capabilities, not third-party skill names", root_skill)
        self.assertIn("runtime-retrieval", source_curation)
        self.assertIn("do not save the provider name", source_curation)

    def test_skills_resolve_data_root_before_topic_file_work(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Resolve the Skrya data root", root_skill)
        self.assertIn("`~/.skrya`", root_skill)
        self.assertIn("`.skrya/data`", root_skill)
        self.assertIn("<skrya-data-root>/topics/<topic-id>/topic.json", digest)
        self.assertIn("skrya data-root --set", root_skill)
        self.assertIn("answer and update the user's storage-location preference", topic_curation)

    def test_source_curation_resolves_internal_topic_id_without_raw_user_id(self) -> None:
        content = (ROOT / "source-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Always resolve an explicit internal `topic-id`", content)
        self.assertIn("do not ask nontechnical users for raw ids", content)
        self.assertNotIn("Always require an explicit `topic-id`", content)

    def test_source_curation_metadata_is_provider_neutral(self) -> None:
        metadata = json.loads((ROOT / "source-curation" / "skill.json").read_text(encoding="utf-8"))

        self.assertIn("runtime retrieval", metadata["description"])
        self.assertIn("provider-neutral", metadata["short_description"])
        self.assertNotIn("RSS-only", metadata["short_description"])

    def test_topic_curation_file_strategy_includes_runtime_retrieval_sources(self) -> None:
        content = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("`runtime-retrieval` capability sources", content)
        self.assertNotIn("confirmed RSS-connectable sources", content)

    def test_digest_consumes_normalized_ingest_not_raw_provider_output(self) -> None:
        content = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("normalized `skrya.ingest.v1`", content)
        self.assertIn("Do not consume raw provider output directly", content)


    def test_skill_descriptions_include_chinese_end_user_trigger_phrases(self) -> None:
        metadata = {
            path.parent.name if path.parent != ROOT else "skrya": json.loads(path.read_text(encoding="utf-8"))
            for path in [
                ROOT / "skill-pack.json",
                ROOT / "topic-curation" / "skill.json",
                ROOT / "request-curation" / "skill.json",
                ROOT / "source-curation" / "skill.json",
                ROOT / "digest" / "skill.json",
                ROOT / "deep-analysis" / "skill.json",
            ]
        }

        self.assertIn("每天帮我关注", metadata["skrya"]["description"])
        self.assertIn("持续跟踪", metadata["topic-curation"]["description"])
        self.assertIn("这条以后少推", metadata["request-curation"]["description"])
        self.assertIn("用某个检索工具抓一下", metadata["source-curation"]["description"])
        self.assertIn("今天有什么重要", metadata["digest"]["description"])
        self.assertIn("展开第 3 条", metadata["deep-analysis"]["description"])

    

    def test_skrya_user_prompt_explains_temporary_provider_binding(self) -> None:
        content = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")

        self.assertIn("临时检索渠道", content)
        self.assertIn("不承诺长期绑定", content)
        self.assertIn("provider-neutral", content)

    def test_topic_curation_guides_ongoing_tracking_into_automation_then_test_run(self) -> None:
        content = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("ongoing tracking", content)
        self.assertIn("recurring digest", content)
        self.assertIn("automation", content)

    def test_scheduled_topical_news_push_routes_to_skrya_before_generic_automation(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        metadata = json.loads((ROOT / "skill-pack.json").read_text(encoding="utf-8"))
        topic_metadata = json.loads((ROOT / "topic-curation" / "skill.json").read_text(encoding="utf-8"))

        for content in [root_skill, topic_curation, agents]:
            self.assertIn("每天早上8点推送", content)
            self.assertIn("官媒", content)
            self.assertIn("generic reminders or automation", content)

        self.assertIn("每天早上8点推送", metadata["description"])
        self.assertIn("官媒信息和新闻", metadata["description"])
        self.assertIn("每天早上8点推送", topic_metadata["description"])
        self.assertIn("官媒信息和新闻", topic_metadata["description"])

    def test_recall_hygiene_guides_agents_to_update_instruction_or_tool_memory(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        full_prompt = (ROOT / "prompt-templates" / "skrya-full.md.tmpl").read_text(encoding="utf-8")
        lite_prompt = (ROOT / "prompt-templates" / "skrya-lite.md.tmpl").read_text(encoding="utf-8")
        user_prompt = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")

        for content in [root_skill, topic_curation, agents, full_prompt, lite_prompt, user_prompt]:
            self.assertIn("AGENTS.md", content)
            self.assertIn("TOOLS.md", content)
            self.assertIn("tools.md", content)
            self.assertIn("persistent", content)

        self.assertIn("missed-routing", root_skill)
        self.assertIn("missed-routing failure", topic_curation)
        self.assertIn("scheduled news pushes route to Skrya/topic-curation", agents)

    def test_root_skill_distinguishes_tracking_setup_from_one_off_research(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("one-off research", content)
        self.assertIn("recurring", content)
        self.assertIn("automation", content)
        self.assertIn("test run", content)
        self.assertIn("ask whether the user wants a test run now", content)
        self.assertIn("automation-capable", content)
        self.assertIn("user-mediated", content)
        self.assertIn("non-automation", content)
        self.assertIn("do not jump straight into a test run or a digest", content)
        self.assertIn("hiding it inside the automation prompt", content)

    

    def test_channel_binding_is_conditional_on_host_channel_concept(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        full_prompt = (ROOT / "prompt-templates" / "skrya-full.md.tmpl").read_text(encoding="utf-8")
        lite_prompt = (ROOT / "prompt-templates" / "skrya-lite.md.tmpl").read_text(encoding="utf-8")
        user_prompt = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")

        for content in [root_skill, topic_curation, digest, agents]:
            self.assertIn("without channel/conversation concepts", content)

        for content in [full_prompt, lite_prompt]:
            self.assertIn("When the host is channel-aware", content)
        self.assertIn("when the host is channel-aware", user_prompt)

        self.assertIn("instead of inventing a channel boundary", root_skill)
        self.assertIn("do not invent a channel boundary", topic_curation)
        self.assertIn("没有通道概念的 agent 不需要伪造通道", user_journeys)

    def test_channel_bound_followups_do_not_use_global_topic_scope(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        full_prompt = (ROOT / "prompt-templates" / "skrya-full.md.tmpl").read_text(encoding="utf-8")
        lite_prompt = (ROOT / "prompt-templates" / "skrya-lite.md.tmpl").read_text(encoding="utf-8")
        user_prompt = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        topic_template = (ROOT / "design" / "topic-template-spec.md").read_text(encoding="utf-8")

        for content in [root_skill, topic_curation, digest, agents, full_prompt, lite_prompt, user_prompt]:
            self.assertIn("delivery-bindings.json", content)

        for content in [root_skill, topic_curation, digest, agents]:
            self.assertIn("current channel", content)
            self.assertIn("do not scan all topics", content.lower())

        self.assertIn("skrya.delivery-bindings.v1", topic_template)
        self.assertIn("host_metadata", topic_template)
        self.assertIn("current-channel-only", user_journeys)
        self.assertIn("扫描所有 topic", user_journeys)
        self.assertIn("Resolve against `delivery-bindings.json` first", user_prompt)

    def test_confirmed_topic_expansion_requires_source_confirmation_before_automation(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        source_curation = (ROOT / "source-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        full_prompt = (ROOT / "prompt-templates" / "skrya-full.md.tmpl").read_text(encoding="utf-8")
        lite_prompt = (ROOT / "prompt-templates" / "skrya-lite.md.tmpl").read_text(encoding="utf-8")
        user_prompt = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        for content in [root_skill, topic_curation, agents]:
            self.assertIn("new or expanded topic", content)
            self.assertIn("source", content)
            self.assertIn("confirmed", content)
        self.assertIn("new or expanded recurring topic", source_curation)
        self.assertIn("source", source_curation)
        self.assertIn("confirmed", source_curation)

        self.assertIn("do not immediately say sources or automation are connected", root_skill)
        self.assertIn("confirm sources next, handle automation/schedule separately", root_skill)
        self.assertIn("produce concrete source groups now", root_skill)
        self.assertIn("Source Confirmation Gate", topic_curation)
        self.assertIn("Do not create or update recurring digest automation until the source plan is confirmed", topic_curation)
        self.assertIn("produce the source plan now", topic_curation)
        self.assertIn("why it fits the confirmed topic", topic_curation)
        self.assertIn("Do not let an agent claim \"已接入\"", source_curation)
        self.assertIn("produce the concrete source plan now", source_curation)
        self.assertIn("which retrieval channel/capability would be used", source_curation)
        self.assertIn("Do not skip source curation", agents)

        for content in [full_prompt, lite_prompt]:
            self.assertIn("require source candidate confirmation", content)
        self.assertIn("propose source candidates and ask for confirmation", user_prompt)

        self.assertIn("旅程 10：确认主题后必须确认信源", user_journeys)
        self.assertIn("BYD，以及新能源汽车，储能", user_journeys)
        self.assertIn("用户确认主题范围后立刻宣布“已接入”", user_journeys)
        self.assertIn("在用户确认信源前写入 `sources.json`", user_journeys)

    def test_source_confirmation_considers_configured_retrieval_channels(self) -> None:
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        source_curation = (ROOT / "source-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        for content in [topic_curation, source_curation, agents]:
            self.assertIn("X", content)
            self.assertIn("WeChat official", content)
            self.assertIn("source-channel", content)

        self.assertIn("web/news search", agents)
        self.assertIn("微信公众号", user_journeys)
        self.assertIn("不能只列网页/新闻检索", user_journeys)
        self.assertIn("Distinguish delivery channels from retrieval/source channels", source_curation)

    def test_topic_setup_proactively_offers_test_run_after_sources_and_automation(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        self.assertIn("proactively ask whether to run one test digest now", root_skill)
        self.assertIn("proactively ask whether the user wants a test run", topic_curation)
        self.assertIn("proactively ask whether to run one test digest now", agents)
        self.assertIn("主动询问用户是否现在试跑一轮", user_journeys)
        self.assertIn("创建成功后不主动询问是否试跑", user_journeys)


    def test_first_use_initialization_is_a_question_only_interaction(self) -> None:
        root_template = (ROOT / "SKILL.md.tmpl").read_text(encoding="utf-8")
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_template = (ROOT / "topic-curation" / "SKILL.md.tmpl").read_text(encoding="utf-8")
        topic_skill = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        user_prompt = (ROOT / "prompt-templates" / "skrya-user.md.tmpl").read_text(encoding="utf-8")
        journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        exact_question = """Skrya 的长期数据保存在哪里？

1. 用户级 `~/.skrya`（推荐，所有项目共享）
2. 当前项目 `.skrya/data`（仅当前项目）
3. 自定义目录（请同时提供路径）"""

        for content in (root_template, root_skill, topic_template, topic_skill, user_prompt):
            self.assertIn("default-home", content)
            self.assertIn(exact_question, content)
            self.assertIn("sole user-facing response", content)

        self.assertIn("旅程 13：首次使用只输出初始化问题", journeys)
        self.assertIn("不要加问候、状态说明、原因解释或下一步预告", journeys)



    def test_digest_template_updates_warn_and_validate_before_save(self) -> None:
        root_template = (ROOT / "SKILL.md.tmpl").read_text(encoding="utf-8")
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        digest_template = (ROOT / "digest" / "SKILL.md.tmpl").read_text(encoding="utf-8")
        digest_skill = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        topic_template = (ROOT / "topic-curation" / "SKILL.md.tmpl").read_text(encoding="utf-8")
        topic_skill = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        eval_bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))
        prompts = [
            (ROOT / "prompt-templates" / name).read_text(encoding="utf-8")
            for name in ("skrya-full.md.tmpl", "skrya-lite.md.tmpl", "skrya-user.md.tmpl")
        ]

        for content in (root_template, root_skill, digest_template, digest_skill, topic_template, topic_skill, agents, *prompts):
            self.assertIn("before", content.lower())
            self.assertIn("template", content.lower())
            self.assertIn("validation", content.lower())

        self.assertIn("提示：你可以创建或调整简报模板的布局和措辞", topic_template)
        self.assertIn("validate-digest-template --file <candidate-path>", topic_template)
        self.assertIn("## Digest Template Create And Update Flow", topic_template)
        self.assertIn("**Create:**", topic_template)
        self.assertIn("**Update:**", topic_template)
        self.assertIn("shared save gate", topic_template)
        self.assertIn("The save gate begins with the completed candidate", topic_template)
        self.assertIn("Do not read an existing topic-specific template as the drafting basis", topic_template)
        self.assertIn("failed validation must not create or overwrite the target", root_template)
        self.assertIn("旅程 14：自建简报模板创建与更新必须先提示并通过保存门禁", user_journeys)
        self.assertEqual(
            {"journey-14-1", "journey-14-2", "journey-14-3", "journey-14-4", "journey-14-5", "journey-14-6"},
            {item["id"] for item in eval_bank["evals"] if item["id"].startswith("journey-14-")},
        )


if __name__ == "__main__":
    unittest.main()
