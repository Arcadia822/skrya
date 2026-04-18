import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.agent_assets import SkillPackBuilder, SkillPackInstaller
from skrya_orchestrator.main import main


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class SkillPackTests(unittest.TestCase):
    def test_builder_generates_root_and_bundled_skills_in_place(self) -> None:
        root = self._make_root("skill-pack-runtime")
        self._copy_template_inputs(root)

        written = SkillPackBuilder(root).build(output_root=root, host_name="workspace")

        self.assertIn(root / "SKILL.md", written)
        self.assertIn(root / "agents" / "openai.yaml", written)
        self.assertIn(root / "skrya" / "SKILL.md", written)
        self.assertIn(root / "skrya" / "agents" / "openai.yaml", written)
        self.assertIn(root / "digest" / "SKILL.md", written)
        self.assertTrue((root / "topic-curation" / "SKILL.md").exists())
        self.assertTrue((root / "skrya" / "SKILL.md").exists())
        self.assertIn("topic-curation", (root / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("topic-curation", (root / "skrya" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("display_name: Digest", (root / "digest" / "agents" / "openai.yaml").read_text(encoding="utf-8"))

    def test_builder_generates_host_prompts_under_dot_skrya(self) -> None:
        root = self._make_root("skill-pack-hosts")
        self._copy_template_inputs(root)

        written = SkillPackBuilder(root).build(output_root=root, host_name="all")

        self.assertIn(root / ".skrya" / "hosts" / "codex" / "prompts" / "skrya-full-AGENTS.md", written)
        self.assertIn(root / ".skrya" / "hosts" / "claude" / "prompts" / "skrya-lite-CLAUDE.md", written)
        self.assertIn(root / ".skrya" / "hosts" / "openclaw" / "prompts" / "skrya-plan-AGENTS.md", written)

    def test_cli_build_skill_pack_command_supports_host_all(self) -> None:
        root = self._make_root("skill-pack-cli")
        self._copy_template_inputs(root)

        stdout = io.StringIO()
        with patch("sys.argv", ["skrya", "build-skill-pack", "--root", str(root), "--host", "all"]):
            with redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertIn("Generated skill pack artifacts for host(s): all", stdout.getvalue())
        self.assertTrue((root / "SKILL.md").exists())
        self.assertTrue((root / "deep-analysis" / "SKILL.md").exists())

    def test_cli_install_skill_pack_uses_symlink_or_copy_into_home(self) -> None:
        root = self._make_root("skill-pack-install")
        home = self._make_root("fake-home")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=home):
            results = SkillPackInstaller(root).install(output_root=root, host_name="auto")

        by_name = {result.skill_name: result for result in results}
        self.assertIn("skrya", by_name)
        self.assertIn("skrya-digest", by_name)
        self.assertIn("skrya-topic-curation", by_name)
        self.assertEqual("codex", by_name["skrya"].host)
        self.assertTrue((home / ".codex" / "skills" / "skrya").exists())
        self.assertTrue((home / ".codex" / "skills" / "skrya-digest").exists())
        self.assertTrue((home / ".codex" / "skills" / "skrya-topic-curation").exists())

    @staticmethod
    def _make_root(name: str) -> Path:
        root = TEST_TEMP_ROOT / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _copy_template_inputs(root: Path) -> None:
        for filename in ["skill-pack.json", "SKILL.md.tmpl", "README.md", "AGENTS.md"]:
            shutil.copy2(ROOT / filename, root / filename)
        shutil.copytree(ROOT / "prompt-templates", root / "prompt-templates")
        for skill_name in [
            "deep-analysis",
            "digest",
            "request-curation",
            "source-curation",
            "topic-curation",
        ]:
            shutil.copytree(ROOT / skill_name, root / skill_name)


if __name__ == "__main__":
    unittest.main()
