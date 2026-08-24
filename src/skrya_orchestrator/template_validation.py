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
    (
        "event_timeline_section",
        r"(?mi)^##\s+(?:事件线时间线更新|Event Timeline Updates)\s*$",
        "missing the event timeline update section",
    ),
    ("thread_box", r"【Thread】", "missing the active Thread line-box marker"),
    (
        "thread_id",
        r"(?i)(?:thread-id|thread id|事件线\s*id)",
        "missing the Thread ID field",
    ),
    ("today_increment", r"(?i)(?:今日增量|today(?:'s)? update)", "missing the verified increment field"),
    ("timeline_position", r"(?i)(?:时间线位置|timeline position)", "missing the timeline position field"),
    ("impact", r"(?i)(?:影响判断|impact)", "missing the impact judgment field"),
    (
        "no_update_review",
        r"(?i)(?:暂无可核验新增|no verified update)",
        "missing the explicit no-verified-update review state",
    ),
    ("latest_state", r"(?i)(?:最新状态|latest state)", "missing the latest Thread state field"),
    (
        "next_observation",
        r"(?i)(?:下一步观察|watch next|next observation)",
        "missing the next observation field",
    ),
    ("digest_item", r"【(?:简讯|Brief)\s*\d+】", "missing the numbered digest-item marker"),
    ("sources", r"(?i)(?:信源|sources?)\s*[：:]", "missing the per-item source field"),
    ("divider", r"(?m)^---\s*$", "missing the divider before the system section"),
    ("system_section", r"(?mi)^##\s+(?:系统提示|System)\s*$", "missing the system section"),
)


def validate_digest_template(content: str) -> DigestTemplateValidationResult:
    issues = tuple(
        TemplateValidationIssue(code=code, message=message)
        for code, pattern, message in _REQUIRED_PATTERNS
        if re.search(pattern, content) is None
    )
    return DigestTemplateValidationResult(issues=issues)
