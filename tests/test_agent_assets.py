import io
import shutil
import tempfile
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
        self.assertNotIn(root / "skrya" / "SKILL.md", written)
        self.assertFalse((root / "skrya" / "SKILL.md").exists())
        self.assertIn(root / "digest" / "SKILL.md", written)
        self.assertTrue((root / "topic-curation" / "SKILL.md").exists())
        self.assertTrue((root / "digest" / "templates" / "default-digest.md").exists())
        self.assertIn(root / "digest" / "templates" / "default-digest.md", written)
        self.assertTrue((root / "source-curation" / "presets" / "ai-llm.yaml").exists())
        self.assertIn(root / "source-curation" / "presets" / "ai-llm.yaml", written)
        self.assertIn("topic-curation", (root / "SKILL.md").read_text(encoding="utf-8"))
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

    def test_repeated_install_keeps_links_under_each_host_skill_directory(self) -> None:
        for host in ("codex", "claude", "openclaw"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                root = base / "source" / "checkout"
                root.mkdir(parents=True)
                home = base / "home"
                self._copy_template_inputs(root)
                skill_directory = home / f".{host}" / "skills"
                names = (
                    "skrya", "skrya-deep-analysis", "skrya-digest",
                    "skrya-request-curation", "skrya-source-curation",
                    "skrya-topic-curation",
                )
                expected_targets = {skill_directory / name for name in names}
                with patch("pathlib.Path.home", return_value=home):
                    installer = SkillPackInstaller(root)
                    first = installer.install(output_root=root, host_name=host)
                    self.assertEqual(expected_targets, {result.target_path for result in first})
                    destinations = {target: target.resolve() for target in expected_targets}
                    for _ in range(2):
                        repeated = installer.install(output_root=root, host_name=host)
                        self.assertEqual(
                            {root}, set(root.parent.iterdir()),
                            "Reinstall must not create aliases beside the source checkout",
                        )
                        self.assertEqual(expected_targets, {result.target_path for result in repeated})
                        self.assertEqual(expected_targets, set(skill_directory.iterdir()))
                        for target, destination in destinations.items():
                            self.assertTrue(target.is_symlink())
                            self.assertEqual(destination, target.resolve())

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

    def test_fresh_symlink_install_exposes_single_umbrella_and_bundled_skills(self) -> None:
        root = self._make_root("skill-pack-fresh-symlink")
        home = self._make_root("fake-home-fresh")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.home", return_value=home):
            results = SkillPackInstaller(root).install(output_root=root, host_name="codex")

        skills_dir = home / ".codex" / "skills"
        installed_names = {entry.name for entry in skills_dir.iterdir()}
        expected_names = {
            "skrya",
            "skrya-deep-analysis",
            "skrya-digest",
            "skrya-request-curation",
            "skrya-source-curation",
            "skrya-topic-curation",
        }
        self.assertEqual(expected_names, installed_names)
        self.assertTrue((skills_dir / "skrya" / "SKILL.md").exists())
        self.assertFalse((skills_dir / "skrya" / "skrya" / "SKILL.md").exists())
        for skill in ("deep-analysis", "digest", "request-curation", "source-curation", "topic-curation"):
            self.assertTrue((skills_dir / f"skrya-{skill}" / "SKILL.md").exists())
        self.assertTrue((skills_dir / "skrya" / "source-curation" / "presets" / "ai-llm.yaml").exists())

    def test_repeated_install_preserves_single_umbrella_and_reentry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "checkout"
            root.mkdir()
            home = base / "home"
            self._copy_template_inputs(root)
            (home / ".codex").mkdir(parents=True, exist_ok=True)
            before = set(root.parent.iterdir())

            with patch("pathlib.Path.home", return_value=home):
                installer = SkillPackInstaller(root)
                installer.install(output_root=root, host_name="codex")
                second_results = installer.install(output_root=root, host_name="codex")

            skills_dir = home / ".codex" / "skills"
            modes = {r.skill_name: r.mode for r in second_results}
            self.assertEqual("in-place", modes["skrya"])
            self.assertTrue((skills_dir / "skrya" / "SKILL.md").exists())
            self.assertFalse((skills_dir / "skrya" / "skrya" / "SKILL.md").exists())
            self.assertEqual(
                before,
                set(root.parent.iterdir()),
                "Reinstall must not create aliases beside checkout",
            )

    def test_physical_copy_install_exposes_single_umbrella_and_bundled_skills(self) -> None:
        root = self._make_root("skill-pack-copy")
        home = self._make_root("fake-home-copy")
        self._copy_template_inputs(root)
        (home / ".codex").mkdir(parents=True, exist_ok=True)

        def fail_symlink(self_path: Path, target: Path, target_is_directory: bool = False) -> None:
            raise OSError("Symlink not supported on this filesystem")

        with patch("pathlib.Path.home", return_value=home), patch.object(Path, "symlink_to", new=fail_symlink):
            results = SkillPackInstaller(root).install(output_root=root, host_name="codex")

        by_name = {r.skill_name: r for r in results}
        self.assertEqual("copy", by_name["skrya"].mode)
        skrya_target = home / ".codex" / "skills" / "skrya"
        self.assertTrue(skrya_target.is_dir())
        self.assertFalse(skrya_target.is_symlink())
        self.assertTrue((skrya_target / "SKILL.md").exists())
        self.assertFalse((skrya_target / "skrya" / "SKILL.md").exists())
        self.assertTrue((skrya_target / "source-curation" / "presets" / "ai-llm.yaml").exists())
        for skill in ("deep-analysis", "digest", "request-curation", "source-curation", "topic-curation"):
            self.assertTrue((home / ".codex" / "skills" / f"skrya-{skill}" / "SKILL.md").exists())

    def test_legacy_upgrade_repairs_duplicate_without_losing_evals_or_custom(self) -> None:
        root = self._make_root("skill-pack-legacy-upgrade")
        self._copy_template_inputs(root)

        legacy_dir = root / "skrya"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "SKILL.md").write_text(
            "---\nname: skrya\ndescription: legacy umbrella\n---\n"
            "<!-- AUTO-GENERATED from SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->\n\n"
            "Legacy body",
            encoding="utf-8",
        )
        (legacy_dir / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "agents" / "openai.yaml", legacy_dir / "agents" / "openai.yaml")
        (legacy_dir / "evals").mkdir(parents=True, exist_ok=True)
        evals_file = legacy_dir / "evals" / "evals.json"
        evals_file.write_text('{"tier": "llm-only"}', encoding="utf-8")
        custom_file = legacy_dir / "custom_notes.txt"
        custom_file.write_text("user notes must survive", encoding="utf-8")

        written = SkillPackBuilder(root).build_runtime_pack(root)

        self.assertIn(root / "SKILL.md", written)
        self.assertFalse((legacy_dir / "SKILL.md").exists())
        self.assertFalse((legacy_dir / "agents" / "openai.yaml").exists())
        self.assertFalse((legacy_dir / "agents").exists())
        self.assertTrue(evals_file.exists())
        self.assertEqual('{"tier": "llm-only"}', evals_file.read_text(encoding="utf-8"))
        self.assertTrue(custom_file.exists())
        self.assertEqual("user notes must survive", custom_file.read_text(encoding="utf-8"))
        self.assertTrue(legacy_dir.exists(), "Legacy directory with custom content must not be deleted")

    def test_custom_content_protection_refuses_unknown_nested_entry(self) -> None:
        root = self._make_root("skill-pack-custom-protection")
        self._copy_template_inputs(root)

        legacy_dir = root / "skrya"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        unknown_skill = legacy_dir / "SKILL.md"
        unknown_skill.write_text(
            "---\nname: my-custom-agent\ndescription: custom agent\n---\nCustom instructions without generated tag.",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as ctx:
            SkillPackBuilder(root).build_runtime_pack(root)

        self.assertIn("Refusing to remove unknown conflicting nested entry", str(ctx.exception))
        self.assertTrue(unknown_skill.exists(), "Conflicting unknown nested entry must be preserved")

    def test_mixed_generated_skill_and_custom_yaml_deletes_nothing(self) -> None:
        root = self._make_root("skill-pack-mixed-conflict")
        self._copy_template_inputs(root)

        legacy_dir = root / "skrya"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_skill = legacy_dir / "SKILL.md"
        legacy_skill.write_text(
            "---\nname: skrya\ndescription: legacy umbrella\n---\n"
            "<!-- AUTO-GENERATED from SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->\n\n"
            "Legacy body",
            encoding="utf-8",
        )
        custom_openai = legacy_dir / "agents" / "openai.yaml"
        custom_openai.parent.mkdir(parents=True, exist_ok=True)
        custom_openai.write_text("interface:\n  display_name: my-custom-agent\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            SkillPackBuilder(root).build_runtime_pack(root)

        self.assertIn("Refusing to remove unknown conflicting nested entry", str(ctx.exception))
        self.assertTrue(legacy_skill.exists(), "Generated SKILL.md must survive an openai.yaml conflict")
        self.assertEqual(
            "interface:\n  display_name: my-custom-agent\n",
            custom_openai.read_text(encoding="utf-8"),
        )

    def test_repair_validates_openai_metadata_against_canonical_counterpart(self) -> None:
        root = self._make_root("skill-pack-openai-validation")
        self._copy_template_inputs(root)

        legacy_dir = root / "skrya"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "agents").mkdir(parents=True, exist_ok=True)
        legacy_openai = legacy_dir / "agents" / "openai.yaml"
        legacy_openai.write_text(
            "interface:\n  display_name: skrya\n  short_description: desc\npolicy:\n  allow_implicit_invocation: true\n",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as ctx:
            SkillPackBuilder(root).build_runtime_pack(root)

        self.assertIn("Refusing to remove unknown conflicting nested entry", str(ctx.exception))
        self.assertTrue(legacy_openai.exists(), "Metadata that fails canonical validation must be preserved")

    def test_repair_refuses_symlinked_agents_dir_without_deleting_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "checkout"
            root.mkdir()
            self._copy_template_inputs(root)

            outside_agents = base / "outside-agents"
            outside_agents.mkdir()
            outside_openai = outside_agents / "openai.yaml"
            outside_openai.write_text("interface:\n  display_name: skrya\n", encoding="utf-8")

            legacy_dir = root / "skrya"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_skill = legacy_dir / "SKILL.md"
            legacy_skill.write_text(
                "---\nname: skrya\ndescription: legacy umbrella\n---\n"
                "<!-- AUTO-GENERATED from SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->\n\n"
                "Legacy body",
                encoding="utf-8",
            )
            (legacy_dir / "agents").symlink_to(outside_agents, target_is_directory=True)

            with self.assertRaises(ValueError) as ctx:
                SkillPackBuilder(root).build_runtime_pack(root)

            self.assertIn("agents entry", str(ctx.exception))
            self.assertTrue(outside_openai.exists(), "Repair must never delete through a directory symlink")
            self.assertTrue(legacy_skill.exists(), "No file may be deleted when a conflict refuses the repair")

    def test_installer_refuses_to_overwrite_another_pack_target(self) -> None:
        root = self._make_root("skill-pack-refuse-overwrite")
        home = self._make_root("fake-home-refuse")
        self._copy_template_inputs(root)
        foreign_target = home / ".codex" / "skills" / "skrya"
        foreign_target.mkdir(parents=True, exist_ok=True)
        (foreign_target / "SKILL.md").write_text("---\nname: foreign-pack\n---\nForeign content", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=home):
            with self.assertRaises(FileExistsError) as ctx:
                SkillPackInstaller(root).install(output_root=root, host_name="codex")

        self.assertIn("Refusing to overwrite existing install target", str(ctx.exception))
        self.assertEqual(
            "---\nname: foreign-pack\n---\nForeign content",
            (foreign_target / "SKILL.md").read_text(encoding="utf-8"),
        )

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
