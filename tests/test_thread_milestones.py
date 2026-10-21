from pathlib import Path
import sys
import unittest

SRC_DIR = Path(__file__).parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skrya_orchestrator.thread_milestones import recorded_date, select_milestones


class ThreadMilestonesTests(unittest.TestCase):
    def test_recorded_date_parses_complete_iso_dates(self):
        self.assertEqual(recorded_date("2026-04-25"), "2026-04-25")
        self.assertEqual(recorded_date("2026-10-16T08:30:00+08:00"), "2026-10-16")
        self.assertEqual(recorded_date("2026-12-31T23:59:59Z"), "2026-12-31")

    def test_recorded_date_parses_complete_rfc_dates(self):
        self.assertEqual(recorded_date("Sat, 25 Apr 2026 14:30:00 GMT"), "2026-04-25")
        self.assertEqual(recorded_date("Fri, 16 Oct 2026 09:15:00 +0900"), "2026-10-16")
        self.assertEqual(recorded_date("25 Apr 2026 12:00:00 -0400"), "2026-04-25")

    def test_recorded_date_rejects_truncated_rfc_and_invalid_values(self):
        self.assertEqual(recorded_date("Sat, 25 Ap"), "")
        self.assertEqual(recorded_date("2026-04"), "")
        self.assertEqual(recorded_date(""), "")
        self.assertEqual(recorded_date(None), "")
        self.assertEqual(recorded_date("not-a-date"), "")

    def test_select_milestones_requires_explicit_nonempty_milestone_reason(self):
        timeline = [
            {
                "date": "2026-04-25",
                "headline": "例行发布会",
                "sources": ["https://example.org/press"],
            },
            {
                "date": "2026-04-26",
                "headline": "法案正式签署",
                "milestone_reason": "关键法案正式签署",
                "sources": ["https://example.org/signed"],
            },
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["headline"], "法案正式签署")
        self.assertEqual(selected[0]["milestone_reason"], "关键法案正式签署")

    def test_select_milestones_rejects_defective_dates_and_non_http_sources(self):
        timeline = [
            {
                "date": "invalid-date",
                "headline": "日期损坏条目",
                "milestone_reason": "重要但日期无效",
                "sources": ["https://example.org/valid"],
            },
            {
                "date": "2026-05-01",
                "headline": "非 HTTP 信源",
                "milestone_reason": "重要但信源非 http",
                "sources": ["internal-memo"],
            },
            {
                "date": "2026-05-02",
                "headline": "空信源列表",
                "milestone_reason": "重要但缺少信源",
                "sources": [],
            },
            {
                "date": "2026-05-03",
                "headline": "有效里程碑",
                "milestone_reason": "有效且完整",
                "sources": ["https://example.org/valid"],
            },
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["headline"], "有效里程碑")
        self.assertEqual(selected[0]["sources"], ["https://example.org/valid"])

    def test_select_milestones_title_and_date_priorities_with_basis(self):
        timeline = [
            {
                "date": "2026-04-01",
                "milestone_date": "2026-04-15",
                "milestone_date_basis": "官方发布会公开声明日期",
                "title": "原始标题",
                "headline": "媒体报道标题",
                "milestone_title": "精简里程碑标题",
                "milestone_reason": "里程碑确立",
                "sources": ["https://example.org/source"],
            }
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["date"], "2026-04-15")
        self.assertEqual(selected[0]["headline"], "精简里程碑标题")

    def test_select_milestones_rejects_override_missing_basis(self):
        timeline = [
            {
                "date": "2026-04-01",
                "milestone_date": "2026-04-15",
                "milestone_reason": "里程碑确立但未给出日期依据",
                "sources": ["https://example.org/source"],
            }
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 0)

    def test_select_milestones_deduplicates_same_date_and_headline(self):
        timeline = [
            {
                "date": "2026-04-20",
                "headline": "大法院长任命案通过",
                "milestone_reason": "国会表决通过",
                "sources": ["https://example.org/source-a"],
            },
            {
                "date": "2026-04-20",
                "headline": "大法院长任命案通过",
                "milestone_reason": "另一媒体相同报道",
                "sources": ["https://example.org/source-b"],
            },
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["sources"], ["https://example.org/source-a"])

    def test_select_milestones_sorts_chronologically(self):
        timeline = [
            {
                "date": "2026-08-01",
                "headline": "第三阶段",
                "milestone_reason": "阶段3",
                "sources": ["https://example.org/s3"],
            },
            {
                "date": "2026-03-01",
                "headline": "第一阶段",
                "milestone_reason": "阶段1",
                "sources": ["https://example.org/s1"],
            },
            {
                "date": "2026-05-15",
                "headline": "第二阶段",
                "milestone_reason": "阶段2",
                "sources": ["https://example.org/s2"],
            },
        ]
        selected = select_milestones(timeline)
        dates = [entry["date"] for entry in selected]
        self.assertEqual(dates, ["2026-03-01", "2026-05-15", "2026-08-01"])

    def test_select_milestones_does_not_mutate_original_timeline(self):
        original_entry = {
            "date": "2026-04-01",
            "headline": "原始标题",
            "milestone_reason": "原因",
            "sources": [{"url": "https://example.org/s1"}],
            "unknown_custom_field": 42,
        }
        timeline = [original_entry]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 1)
        self.assertIsInstance(original_entry["sources"][0], dict)
        self.assertEqual(original_entry["unknown_custom_field"], 42)
        self.assertEqual(selected[0]["unknown_custom_field"], 42)

    def test_select_milestones_retains_all_early_milestones_without_truncation(self):
        timeline = [
            {
                "date": f"2026-01-{i:02d}",
                "headline": f"里程碑-{i}",
                "milestone_reason": f"重要进展 {i}",
                "sources": [f"https://example.org/s{i}"],
            }
            for i in range(1, 15)
        ]
        selected = select_milestones(timeline)
        self.assertEqual(len(selected), 14)
        self.assertEqual(selected[0]["headline"], "里程碑-1")
        self.assertEqual(selected[-1]["headline"], "里程碑-14")


if __name__ == "__main__":
    unittest.main()
