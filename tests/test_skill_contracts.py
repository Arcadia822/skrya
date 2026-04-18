import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_readme_documents_generated_agent_assets(self) -> None:
        readme_path = ROOT / "README.md"

        content = readme_path.read_text(encoding="utf-8")
        self.assertIn("# Skrya", content)
        self.assertIn("skills-src/", content)
        self.assertIn("prompt-templates/", content)
        self.assertIn("build-agent-assets", content)
        self.assertIn("agent-hosts/", content)
        self.assertIn("python -m skrya_orchestrator.main", content)
        self.assertIn("skrya-agent-host-bridge-design.md", content)

    def test_agents_routes_unconfigured_topic_info_requests_to_topic_curation(self) -> None:
        agents_path = ROOT / "AGENTS.md"

        content = agents_path.read_text(encoding="utf-8")
        self.assertIn("important information", content)
        self.assertIn("without first naming an existing configured `topic-id`", content)
        self.assertIn("route to `topic-curation` first instead of answering directly", content)
        self.assertIn("clarify the user's crawling or tracking request", content)
        self.assertIn("some company, industry, market, product category, or theme", content)
        self.assertIn("Do not skip straight to digest generation or one-off research", content)

    def test_topic_curation_skill_exists_and_generalizes_intent_before_creating_or_sourcing(self) -> None:
        skill_path = ROOT / "skills" / "topic-curation" / "SKILL.md"

        self.assertTrue(skill_path.exists(), "topic-curation skill should exist")

        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("topic-id", content)
        self.assertIn("brief.json", content)
        self.assertIn("先把用户真正想持续看到的简报内容聊清楚", content)
        self.assertIn("再把用户的话抽象成稳定的配置语义", content)
        self.assertIn("Do not create a new topic shell before the briefing intent is clear enough.", content)
        self.assertIn("Do not answer a broad unconfigured-topic info request with a direct digest first.", content)
        self.assertIn("sources.json", content)
        self.assertIn("确认", content)
        self.assertIn("request", content)
        self.assertIn("信源", content)
        self.assertIn("有 RSS，可接入", content)
        self.assertIn("没有 RSS，当前不可接入", content)
        self.assertIn("important information", content)
        self.assertIn("some company, industry, market, product category, or theme", content)
        self.assertNotIn("BYD", content)

    def test_request_and_source_curation_skills_exist(self) -> None:
        request_skill = ROOT / "skills" / "request-curation" / "SKILL.md"
        source_skill = ROOT / "skills" / "source-curation" / "SKILL.md"

        self.assertTrue(request_skill.exists(), "request-curation skill should exist")
        self.assertTrue(source_skill.exists(), "source-curation skill should exist")
        self.assertIn("brief.json", request_skill.read_text(encoding="utf-8"))
        self.assertIn("sources.json", source_skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
