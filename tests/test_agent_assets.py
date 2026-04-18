import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.agent_assets import AssetBuilder
from skrya_orchestrator.main import main


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class AgentAssetTests(unittest.TestCase):
    def test_builder_generates_workspace_skills_and_metadata_from_source_templates(self) -> None:
        root = self._make_root("agent-assets-workspace")
        self._copy_template_inputs(root)

        written = AssetBuilder(root).build(output_root=root, host_name="workspace")

        self.assertIn(root / "skills" / "request-curation" / "SKILL.md", written)
        self.assertIn(root / "skills" / "source-curation" / "SKILL.md", written)
        digest_skill = root / "skills" / "digest" / "SKILL.md"
        self.assertTrue(digest_skill.exists())
        self.assertIn("Always require an explicit `topic-id`.", digest_skill.read_text(encoding="utf-8"))
        digest_metadata = root / "skills" / "digest" / "agents" / "openai.yaml"
        self.assertTrue(digest_metadata.exists())
        self.assertIn("display_name: Digest", digest_metadata.read_text(encoding="utf-8"))

    def test_builder_generates_host_specific_roots_and_prompt_packs(self) -> None:
        root = self._make_root("agent-assets-hosts")
        self._copy_template_inputs(root)

        written = AssetBuilder(root).build(output_root=root, host_name="all")

        self.assertIn(root / ".agents" / "skills" / "digest" / "SKILL.md", written)
        self.assertIn(root / ".claude" / "skills" / "digest" / "SKILL.md", written)
        self.assertIn(root / ".openclaw" / "skills" / "digest" / "SKILL.md", written)
        self.assertTrue((root / "agent-hosts" / "codex" / "skrya-full-AGENTS.md").exists())
        self.assertTrue((root / "agent-hosts" / "claude" / "skrya-lite-CLAUDE.md").exists())
        self.assertTrue((root / "agent-hosts" / "openclaw" / "skrya-plan-AGENTS.md").exists())

    def test_cli_build_agent_assets_command_supports_host_all(self) -> None:
        root = self._make_root("agent-assets-cli")
        self._copy_template_inputs(root)

        stdout = io.StringIO()
        with patch(
            "sys.argv",
            ["skrya", "build-agent-assets", "--root", str(root), "--host", "all"],
        ):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn("Generated assets for host(s): all", stdout.getvalue())
        self.assertTrue((root / "skills" / "topic-curation" / "SKILL.md").exists())
        self.assertTrue((root / ".agents" / "skills" / "deep-analysis" / "SKILL.md").exists())

    @staticmethod
    def _make_root(name: str) -> Path:
        root = TEST_TEMP_ROOT / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _copy_template_inputs(root: Path) -> None:
        shutil.copytree(ROOT / "skills-src", root / "skills-src")
        shutil.copytree(ROOT / "prompt-templates", root / "prompt-templates")


if __name__ == "__main__":
    unittest.main()
