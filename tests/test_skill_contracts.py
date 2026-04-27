import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_readme_documents_installable_skill_pack_model(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("# Skrya", content)
        self.assertIn("[English](README.en.md)", content)
        self.assertIn("skill-pack.json", content)
        self.assertIn("build-skill-pack", content)
        self.assertIn("install-skill-pack", content)
        self.assertIn(".skrya/hosts/", content)
        self.assertIn("data-root", content)
        self.assertIn("~/.skrya", content)
        self.assertIn(".skrya/data", content)
        self.assertIn("setup", content)
        self.assertIn("thread --topic", content)
        self.assertIn("refresh-threads --topic", content)
        self.assertIn("thread-seeds.json", content)
        self.assertIn("topics/new-energy-vehicles/", content)
        self.assertIn("docs/domain-model.md", content)
        self.assertIn("docs/upgrade.md", content)
        self.assertIn("uninstall-skill-pack", content)
        self.assertIn("skills-keep-data", content)
        self.assertIn("data-keep-skills", content)
        self.assertIn("complete", content)

    def test_english_readme_is_available_from_homepage(self) -> None:
        zh_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        en_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")

        self.assertIn("**语言 / Language:** 简体中文 | [English](README.en.md)", zh_readme)
        self.assertIn("**Language:** [Chinese](README.md) | English", en_readme)
        self.assertIn("Topic-driven briefing workspace", en_readme)
        self.assertIn("## Language Policy", en_readme)
        self.assertIn("## Installation", en_readme)
        self.assertIn("## Uninstall", en_readme)
        self.assertIn("uninstall-skill-pack", en_readme)
        self.assertNotRegex(en_readme, r"[\u4e00-\u9fff]")

    def test_new_energy_vehicles_topic_fixture_models_thread_journey(self) -> None:
        topic_dir = ROOT / "topics" / "new-energy-vehicles"

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

    def test_thread_docs_align_on_user_flow_and_runtime_artifacts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        threads = (ROOT / "docs" / "threads.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        self.assertIn("帮我持续跟比亚迪闪充站这条线；以后有新进展就接着往下讲", readme)
        self.assertIn("<skrya-data-root>/topics/new-energy-vehicles/thread-seeds.json", readme)
        self.assertIn("<skrya-data-root>/runs/new-energy-vehicles/threads/latest-threads.json", readme)
        self.assertIn('thread --topic new-energy-vehicles --thread "比亚迪闪充站"', readme)
        self.assertIn("旅程 6：持续事件的时间线追踪", readme)
        self.assertIn("旅程 6：持续事件的时间线追踪", threads)
        self.assertIn("thread更新不要压成一行泛泛而谈", threads)
        self.assertIn("┌─ **【thread】比亚迪闪充站**", threads)
        self.assertNotIn("今天命中的简讯：1、2", threads)
        self.assertIn("A. 详细分析指定今日简讯", threads)
        self.assertIn("refresh-threads", threads)
        self.assertIn("帮我持续跟比亚迪闪充站这条线；以后有新进展就接着往下讲", user_journeys)
        self.assertIn("thread` seed", user_journeys)
        self.assertIn("展开这条线", user_journeys)

    def test_upgrade_and_domain_model_docs_exist(self) -> None:
        domain_model = (ROOT / "docs" / "domain-model.md").read_text(encoding="utf-8")
        upgrade = (ROOT / "docs" / "upgrade.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("| `thread` |", domain_model)
        self.assertIn("| `channel` |", domain_model)
        self.assertIn("upgrade --root . --migrate-thread-naming", upgrade)
        self.assertIn("current Skrya version", digest)
        self.assertIn("agent framework/version and LLM model only when the host exposes them", digest)

    def test_uninstall_journey_and_skill_contract_are_documented(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

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

    def test_agents_routes_unconfigured_topic_info_requests_to_topic_curation(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("important information", content)
        self.assertIn("without first naming an existing configured `topic-id`", content)
        self.assertIn("route to `topic-curation` first instead of answering directly", content)
        self.assertIn("clarify the user's crawling or tracking request", content)
        self.assertIn("company, industry, market, product category, or theme", content)

    def test_root_and_bundled_skill_docs_exist(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").exists(), "root umbrella skill should exist")
        self.assertTrue((ROOT / "README.en.md").exists(), "English README should exist")
        self.assertTrue((ROOT / "skrya" / "SKILL.md").exists(), "installer-facing skrya skill should exist")
        self.assertTrue((ROOT / "topic-curation" / "SKILL.md").exists(), "topic-curation skill should exist")
        self.assertTrue((ROOT / "request-curation" / "SKILL.md").exists(), "request-curation skill should exist")
        self.assertTrue((ROOT / "source-curation" / "SKILL.md").exists(), "source-curation skill should exist")
        self.assertTrue((ROOT / "digest" / "SKILL.md").exists(), "digest skill should exist")
        self.assertTrue((ROOT / "deep-analysis" / "SKILL.md").exists(), "deep-analysis skill should exist")
        self.assertTrue((ROOT / "CONTRIBUTING.md").exists(), "contribution guide should exist")
        self.assertTrue((ROOT / "LICENSE").exists(), "license should exist")

    def test_license_and_contributing_are_documented(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("CONTRIBUTING.md", readme)
        self.assertIn("MIT", readme)
        self.assertIn("build-skill-pack", contributing)
        self.assertIn("Use `thread`, not `event-thread`", contributing)
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

    def test_language_policy_is_topic_scoped_and_bilingual(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        english_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")

        for content in [root_skill, agents, topic_curation, readme, english_readme]:
            self.assertIn("topic.json.language", content)

        self.assertIn("Do not set output language at installation time", root_skill)
        self.assertNotIn("Default output language is Chinese", agents)
        self.assertIn("Supported output languages are Chinese and English", root_skill)
        self.assertIn("Chinese and English output", english_readme)
        self.assertIn("English format: `# YYYY-MM-DD | Topic Name | Daily Briefing`", digest)
        self.assertIn("`## System` for English", digest)

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

    def test_skills_route_digest_feedback_into_durable_topic_memory(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        request_curation = (ROOT / "request-curation" / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")

        for phrase in [
            "A <numbers>",
            "B <numbers>",
            "C <numbers",
            "thread-seeds.json",
            "为什么没有",
            "这个很重要",
            "ambiguous shorthand entities",
            "repeated identical instructions",
            "long-running provenance",
        ]:
            self.assertIn(phrase, root_skill)

        self.assertIn("clarify once, then store", topic_curation)
        self.assertIn("active topic", topic_curation)
        self.assertIn("漏报诊断", request_curation)
        self.assertIn("check latest digest", request_curation)
        self.assertIn("B <numbers>", digest)
        self.assertIn("C <numbers", digest)
        self.assertIn("durable topic memory", digest)

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

    def test_file_names_are_internal_execution_details_in_writing_skills(self) -> None:
        for relative_path in [
            "topic-curation/SKILL.md",
            "request-curation/SKILL.md",
            "source-curation/SKILL.md",
            "digest/SKILL.md",
            "deep-analysis/SKILL.md",
        ]:
            content = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("File names are internal execution details", content, relative_path)
            self.assertIn("do not show file names", content, relative_path)

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

    def test_channel_aware_hosts_keep_digest_delivery_and_resend_in_original_channel(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        topic_curation = (ROOT / "topic-curation" / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        for content in [root_skill, topic_curation, digest, agents]:
            self.assertIn("channel-aware", content)
            self.assertIn("channel", content)
            self.assertIn("cross-channel", content)
            self.assertIn("non-empty", content)

        self.assertIn("Never bundle another channel's topic digest", root_skill)
        self.assertIn("Do not merge or forward another channel's topic digest", topic_curation)
        self.assertIn("Do not bundle unrelated topic digests from other channels", digest)
        self.assertIn("explicit message-tool sending", agents)
        self.assertIn("旅程 9：空日报诊断和补发不能串通道", user_journeys)
        self.assertIn("把“军民融合”这种另一个通道的日报发到韩国时政通道", user_journeys)

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
        self.assertIn("Source Confirmation Gate", topic_curation)
        self.assertIn("Do not create or update recurring digest automation until the source plan is confirmed", topic_curation)
        self.assertIn("Do not let an agent claim \"已接入\"", source_curation)
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

    def test_test_run_uses_digest_template_without_saving_or_chatter(self) -> None:
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        digest = (ROOT / "digest" / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        user_journeys = (ROOT / "docs" / "user-journeys.md").read_text(encoding="utf-8")

        for content in [root_skill, digest, agents]:
            self.assertIn("same digest template", content)
            self.assertIn("## 系统提示", content)
            self.assertIn("Do not", content)
            self.assertIn("latest-digest.md", content)

        self.assertIn("Do not write conversational prefaces", root_skill)
        self.assertIn("Do not append implementation notes", digest)
        self.assertIn("do not save test-run previews by default", digest)
        self.assertIn("A <编号>", root_skill)
        self.assertIn("旅程 11：试跑输出必须等同正式日报模板", user_journeys)
        self.assertIn("不要先发一段“我跑一轮测试”的闲聊", user_journeys)
        self.assertIn("只说“可以回复 A 2”，但不解释 A/B/C 的含义", user_journeys)
        self.assertIn("把测试产物写入或宣称写入 `latest-digest.md`", user_journeys)


if __name__ == "__main__":
    unittest.main()
