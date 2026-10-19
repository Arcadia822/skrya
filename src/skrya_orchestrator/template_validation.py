from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemplateValidationIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DigestTemplateValidationResult:
    issues: tuple[TemplateValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


_REQUIRED_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("title", r"(?m)^#\s+\S", "missing a top-level digest title"),
    ("event_timeline_section", r"(?mi)^##\s+.*(?:持续追踪|事件线|Event Timeline Updates|Ongoing Threads).*$", "missing the active Thread section"),
    ("thread_reference", r"\bT-\d{2,}\b", "missing a visible T-xx reference"),
    ("latest_progress", r"(?i)(?:最新进展|latest developments|latest updates?)", "missing per-news latest developments"),
    ("historical_timeline", r"(?i)(?:历史时间线|historical timeline)", "missing the curated historical timeline"),
    ("no_update_review", r"(?i)(?:暂无可核验新增|no verified update)", "missing the explicit no-verified-update state"),
    ("latest_state", r"(?i)(?:最新状态|latest (?:known )?state)", "missing the latest known Thread state"),
    ("digest_item", r"\bN-\d{2,}\b", "missing a visible N-xx reference"),
    ("sources", r"(?i)(?:来源|信源|sources?)\*{0,2}\s*[：:]", "missing source references"),
    ("operations_section", r"(?mi)^##\s+.*(?:可继续操作|Available actions|Operations).*$", "missing the fixed actions section"),
    ("dig_news", r"(?i)dig:\s*N-\d{2,}", "missing the news analysis action"),
    ("track_news", r"(?i)track:\s*N-\d{2,}", "missing the tracking action"),
    ("dig_thread", r"(?i)dig:\s*T-\d{2,}", "missing the complete-history action"),
    ("write_thread", r"(?i)write:\s*T-\d{2,}", "missing the article draft action"),
    ("feedback", r"(?i)(?:自然语言反馈|natural.language feedback)", "missing natural-language feedback"),
)


def validate_digest_template(content: str) -> DigestTemplateValidationResult:
    issues = [
        TemplateValidationIssue(code=code, message=message)
        for code, pattern, message in _REQUIRED_PATTERNS
        if re.search(pattern, content) is None
    ]
    if re.search(r"[┌└│]", content):
        issues.append(TemplateValidationIssue("ascii_box", "decorative line boxes are not supported"))
    operations = re.search(
        r"(?mis)^##\s+[^\n]*(?:可继续操作|Available actions|Operations)[^\n]*\n(.*?)(?=^##\s|^```|\Z)",
        content,
    )
    if operations:
        entries = re.findall(r"(?m)^\s*[-*]\s+\S.*$", operations.group(1))
        if len(entries) != 5:
            issues.append(TemplateValidationIssue("action_count", "the actions section must contain exactly five entries"))
        if re.search(r"(?i)(?:执行时间|执行状态|模型|版本|execution (?:time|status)|LLM|model:|version:)", operations.group(1)):
            issues.append(TemplateValidationIssue("action_metadata", "runtime metadata does not belong in the actions section"))
    return DigestTemplateValidationResult(issues=tuple(issues))
