import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_readme_documents_installable_skill_pack_model(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("# Skrya", content)
        self.assertIn("skill-pack.json", content)
        self.assertIn("build-skill-pack", content)
        self.assertIn("install-skill-pack", content)
        self.assertIn(".skrya/hosts/", content)
        self.assertIn("setup", content)

    def test_agents_routes_unconfigured_topic_info_requests_to_topic_curation(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("important information", content)
        self.assertIn("without first naming an existing configured `topic-id`", content)
        self.assertIn("route to `topic-curation` first instead of answering directly", content)
        self.assertIn("clarify the user's crawling or tracking request", content)
        self.assertIn("company, industry, market, product category, or theme", content)

    def test_root_and_bundled_skill_docs_exist(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").exists(), "root umbrella skill should exist")
        self.assertTrue((ROOT / "skrya" / "SKILL.md").exists(), "installer-facing skrya skill should exist")
        self.assertTrue((ROOT / "topic-curation" / "SKILL.md").exists(), "topic-curation skill should exist")
        self.assertTrue((ROOT / "request-curation" / "SKILL.md").exists(), "request-curation skill should exist")
        self.assertTrue((ROOT / "source-curation" / "SKILL.md").exists(), "source-curation skill should exist")
        self.assertTrue((ROOT / "digest" / "SKILL.md").exists(), "digest skill should exist")
        self.assertTrue((ROOT / "deep-analysis" / "SKILL.md").exists(), "deep-analysis skill should exist")

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
        self.assertIn("automation-capable", content)
        self.assertIn("user-mediated", content)
        self.assertIn("non-automation", content)
        self.assertIn("test run", content)
        self.assertIn("Do not jump straight into running a digest", content)
        self.assertIn("Do not hide the test run decision inside the automation prompt", content)

    def test_root_skill_distinguishes_tracking_setup_from_one_off_research(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("one-off research", content)
        self.assertIn("recurring", content)
        self.assertIn("automation", content)
        self.assertIn("test run", content)
        self.assertIn("ask whether the user wants a test run now", content)


if __name__ == "__main__":
    unittest.main()
