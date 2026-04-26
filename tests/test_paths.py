import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.paths import resolve_data_root, write_data_root_config


ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = ROOT / "tmp" / "unit-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class DataRootPathTests(unittest.TestCase):
    def test_resolve_data_root_prefers_explicit_then_env_then_workspace_config(self) -> None:
        root = self._make_root("path-priority")
        workspace_data = root / ".skrya" / "data"
        (root / ".skrya").mkdir(parents=True, exist_ok=True)
        (root / ".skrya" / "config.json").write_text(json.dumps({"data_root": ".skrya/data"}), encoding="utf-8")

        self.assertEqual(root / "explicit-data", resolve_data_root(root, "explicit-data").data_root)
        with patch.dict(os.environ, {"SKRYA_DATA_ROOT": str(root / "env-data")}):
            self.assertEqual(root / "env-data", resolve_data_root(root).data_root)

        resolution = resolve_data_root(root)
        self.assertEqual(workspace_data, resolution.data_root)
        self.assertEqual("workspace-config", resolution.source)

    def test_write_data_root_config_can_migrate_workspace_topics_and_runs(self) -> None:
        root = self._make_root("path-migrate")
        (root / "topics" / "ai-browser").mkdir(parents=True)
        (root / "topics" / "ai-browser" / "topic.json").write_text("{}", encoding="utf-8")
        (root / "runs" / "ai-browser").mkdir(parents=True)
        (root / "runs" / "ai-browser" / "latest-digest.md").write_text("# Digest", encoding="utf-8")

        result = write_data_root_config(root, ".skrya/data", scope="workspace", migrate=True)

        self.assertEqual(root / ".skrya" / "data", result.data_root)
        self.assertEqual(root / ".skrya" / "config.json", result.config_path)
        self.assertTrue((result.data_root / "topics" / "ai-browser" / "topic.json").exists())
        self.assertTrue((result.data_root / "runs" / "ai-browser" / "latest-digest.md").exists())

    @staticmethod
    def _make_root(name: str) -> Path:
        root = TEST_TEMP_ROOT / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root


if __name__ == "__main__":
    unittest.main()
