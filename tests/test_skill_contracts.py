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
