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

    def test_installer_configures_host_default_data_root(self) -> None:
        root = self._make_root("skill-pack-data-root")
        home = self._make_root("fake-home-data-root")
        self._copy_template_inputs(root)
        (home / ".openclaw").mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=home):
            results = SkillPackInstaller(root).configure_data_roots(
                output_root=root,
                host_name="openclaw",
                mode="host-default",
            )

        self.assertEqual(1, len(results))
        self.assertEqual(root / ".skrya" / "data", results[0].data_root)
        self.assertEqual(root / ".skrya" / "config.json", results[0].config_path)

    def test_cli_uninstall_skill_pack_can_remove_skills_but_keep_data(self) -> None:
        root = self._make_root("skill-pack-uninstall-skills")
        home = self._make_root("fake-home-uninstall-skills")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)
        data_root = home / ".skrya"
        data_root.mkdir(parents=True)
        (data_root / "topics").mkdir()

        with patch("pathlib.Path.home", return_value=home):
            SkillPackInstaller(root).install(output_root=root, host_name="codex")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["skrya", "uninstall-skill-pack", "--root", str(root), "--host", "codex", "--mode", "skills-keep-data"],
            ):
                with redirect_stdout(stdout):
                    exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertFalse((home / ".codex" / "skills" / "skrya").exists())
        self.assertFalse((home / ".codex" / "skills" / "skrya-digest").exists())
        self.assertTrue((root / "SKILL.md").exists())
        self.assertTrue((data_root / "topics").exists())
        self.assertIn("skill: removed", stdout.getvalue())

    def test_cli_uninstall_skill_pack_can_clear_data_but_keep_skills(self) -> None:
        root = self._make_root("skill-pack-uninstall-data")
        home = self._make_root("fake-home-uninstall-data")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)
        (root / ".skrya").mkdir(parents=True, exist_ok=True)
        (root / ".skrya" / "config.json").write_text('{"data_root": ".skrya/data"}', encoding="utf-8")
        (root / ".skrya" / "data" / "topics").mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=home):
            SkillPackInstaller(root).install(output_root=root, host_name="codex")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["skrya", "uninstall-skill-pack", "--root", str(root), "--host", "codex", "--mode", "data-keep-skills"],
            ):
                with redirect_stdout(stdout):
                    exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertTrue((home / ".codex" / "skills" / "skrya").exists())
        self.assertFalse((root / ".skrya" / "data").exists())
        self.assertFalse((root / ".skrya" / "config.json").exists())
        self.assertIn("data-root: removed", stdout.getvalue())

    def test_uninstall_refuses_to_clear_implicit_default_home_data_root(self) -> None:
        root = self._make_root("skill-pack-uninstall-default-home")
        home = self._make_root("fake-home-uninstall-default-home")
        self._copy_template_inputs(root)
        (home / ".skrya" / "topics").mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=home):
            with self.assertRaisesRegex(ValueError, "Refusing to remove the default Skrya data root"):
                SkillPackInstaller(root).uninstall(
                    output_root=root,
                    host_name="codex",
                    mode="data-keep-skills",
                )

        self.assertTrue((home / ".skrya" / "topics").exists())

    def test_cli_uninstall_skill_pack_complete_removes_marked_global_instruction_note(self) -> None:
        root = self._make_root("skill-pack-uninstall-complete")
        home = self._make_root("fake-home-uninstall-complete")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)
        (root / ".skrya").mkdir(parents=True, exist_ok=True)
        (root / ".skrya" / "config.json").write_text('{"data_root": ".skrya/data"}', encoding="utf-8")
        (root / ".skrya" / "data" / "topics").mkdir(parents=True)
        global_agents = home / ".codex" / "AGENTS.md"
        global_agents.write_text(
            "\n".join(
                [
                    "Keep this unrelated instruction.",
                    "<!-- SKRYA-ROUTING-NOTE:START -->",
                    "Route topical recurring briefings to Skrya.",
                    "<!-- SKRYA-ROUTING-NOTE:END -->",
                    "Keep this too.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch("pathlib.Path.home", return_value=home):
            SkillPackInstaller(root).install(output_root=root, host_name="codex")
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                ["skrya", "uninstall-skill-pack", "--root", str(root), "--host", "codex", "--mode", "complete"],
            ):
                with redirect_stdout(stdout):
                    exit_code = main()

        self.assertEqual(0, exit_code)
        self.assertFalse((home / ".codex" / "skills" / "skrya").exists())
        self.assertFalse((root / ".skrya" / "data").exists())
        self.assertTrue((root / "SKILL.md").exists())
        content = global_agents.read_text(encoding="utf-8")
        self.assertIn("Keep this unrelated instruction.", content)
        self.assertIn("Keep this too.", content)
        self.assertNotIn("SKRYA-ROUTING-NOTE", content)
        self.assertIn("global-instruction: skrya-note-removed", stdout.getvalue())

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
