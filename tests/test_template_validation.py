import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.main import main
from skrya_orchestrator.template_validation import validate_digest_template


ROOT = Path(__file__).resolve().parents[1]


class DigestTemplateValidationTests(unittest.TestCase):
    def test_default_digest_template_satisfies_required_contract(self) -> None:
        content = (ROOT / "digest" / "templates" / "default-digest.md").read_text(encoding="utf-8")

        result = validate_digest_template(content)

        self.assertTrue(result.valid)
        self.assertEqual((), result.issues)

    def test_template_without_event_timeline_contract_is_rejected(self) -> None:
        content = """# YYYY-MM-DD | Topic | Daily Briefing

┌─ **【Brief 1】Title**
│ Summary
│ Sources: [Source](url)
└

---

## System
"""

        result = validate_digest_template(content)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("event_timeline_section", codes)
        self.assertIn("latest_state", codes)
        self.assertIn("no_update_review", codes)

    def test_template_without_no_update_latest_state_is_rejected(self) -> None:
        content = (ROOT / "digest" / "templates" / "default-digest.md").read_text(encoding="utf-8")
        content = content.replace("复核结果：已检查，本轮暂无可核验新增。", "复核已完成。")
        content = content.replace("最新状态：YYYY-MM-DD：最近时间线标题与简要状态。", "最近记录仍然有效。")
        content = content.replace("latest known timeline state", "prior timeline context")
        content = content.replace("latest known timeline date", "prior timeline date")

        result = validate_digest_template(content)

        codes = {issue.code for issue in result.issues}
        self.assertIn("no_update_review", codes)
        self.assertIn("latest_state", codes)

    def test_cli_returns_nonzero_and_lists_missing_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            template_path = Path(tmp_dir) / "candidate.md"
            template_path.write_text("# Custom digest\n", encoding="utf-8")
            original = template_path.read_text(encoding="utf-8")
            stdout = io.StringIO()

            with patch("sys.argv", ["skrya", "validate-digest-template", "--file", str(template_path)]):
                with redirect_stdout(stdout):
                    exit_code = main()
            preserved = template_path.read_text(encoding="utf-8")

        self.assertEqual(1, exit_code)
        output = stdout.getvalue()
        self.assertIn("Digest template invalid", output)
        self.assertIn("event_timeline_section", output)
        self.assertIn("latest_state", output)
        self.assertEqual(original, preserved)


if __name__ == "__main__":
    unittest.main()
