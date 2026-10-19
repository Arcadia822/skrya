import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from skrya_orchestrator.main import main
from skrya_orchestrator.template_validation import validate_digest_template


CANDIDATE = """# YYYY-MM-DD | Topic | Daily Briefing

## Event Timeline Updates
### T-01 Continuing event
Latest developments: linked current reporting.
Historical timeline: explicitly curated milestones.
No verified update: show the latest known state.

## News
### N-01 News title
Sources: [Publisher](https://example.com/news)

## Available actions
- dig: N-01
- track: N-02
- dig: T-01
- write: T-01
- Natural-language feedback
"""


class DigestTemplateValidationTests(unittest.TestCase):
    def test_accepts_modern_contract_without_internal_thread_id_or_line_box(self) -> None:
        self.assertTrue(validate_digest_template(CANDIDATE).valid)

    def test_missing_active_thread_contract_is_rejected(self) -> None:
        candidate = CANDIDATE.replace(
            "## Event Timeline Updates\n### T-01 Continuing event\n"
            "Latest developments: linked current reporting.\n"
            "Historical timeline: explicitly curated milestones.\n"
            "No verified update: show the latest known state.\n", ""
        )
        result = validate_digest_template(candidate)
        codes = {issue.code for issue in result.issues}
        self.assertFalse(result.valid)
        self.assertTrue({"event_timeline_section", "latest_progress", "historical_timeline", "latest_state"} <= codes)

    def test_each_followup_is_required_independently(self) -> None:
        for action, code in [("- dig: N-01", "dig_news"), ("- track: N-02", "track_news"),
                             ("- dig: T-01", "dig_thread"), ("- write: T-01", "write_thread"),
                             ("- Natural-language feedback", "feedback")]:
            with self.subTest(action=action):
                result = validate_digest_template(CANDIDATE.replace(action, ""))
                self.assertIn(code, {issue.code for issue in result.issues})

    def test_rejects_extra_actions_and_runtime_metadata(self) -> None:
        extra = validate_digest_template(CANDIDATE + "- Extra operation\n")
        self.assertIn("action_count", {issue.code for issue in extra.issues})
        metadata = validate_digest_template(CANDIDATE + "Execution time: today\n")
        self.assertIn("action_metadata", {issue.code for issue in metadata.issues})

    def test_rejects_decorative_boxes_even_with_all_required_fields(self) -> None:
        result = validate_digest_template(CANDIDATE + "\n┌─ news\n│ facts\n└\n")
        self.assertIn("ascii_box", {issue.code for issue in result.issues})

    def test_rejects_omission_of_no_update_state(self) -> None:
        result = validate_digest_template(CANDIDATE.replace("No verified update: show the latest known state.", ""))
        self.assertTrue({"no_update_review", "latest_state"} <= {issue.code for issue in result.issues})

    def test_cli_failure_does_not_overwrite_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "candidate.md"
            original = "# Custom digest\n"
            path.write_text(original, encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["skrya", "validate-digest-template", "--file", str(path)]):
                with redirect_stdout(stdout):
                    code = main()
            self.assertEqual(1, code)
            self.assertIn("event_timeline_section", stdout.getvalue())
            self.assertEqual(original, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
