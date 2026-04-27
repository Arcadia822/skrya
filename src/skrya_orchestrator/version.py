from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


__version__ = "0.1.0"


@dataclass(frozen=True)
class VersionCheck:
    local_version: str
    local_revision: str | None = None
    remote_revision: str | None = None

    @property
    def has_remote_update(self) -> bool:
        return bool(self.local_revision and self.remote_revision and self.local_revision != self.remote_revision)


def runtime_metadata_lines(root: Path | str) -> list[str]:
    lines = [f"- Skrya：{__version__}"]

    agent = _agent_framework_label()
    if agent:
        lines.append(f"- Agent：{agent}")

    model = _first_env("SKRYA_LLM_MODEL", "OPENAI_MODEL", "ANTHROPIC_MODEL", "MODEL")
    if model:
        lines.append(f"- LLM：{model}")

    check = check_latest_version(root)
    if check.has_remote_update:
        lines.append("- 版本检查：发现 Skrya 有可见新版本。回复“更新 Skrya”后，我会先执行升级流程。")
    return lines


def check_latest_version(root: Path | str) -> VersionCheck:
    root = Path(root).resolve(strict=False)
    local_revision = _git_output(root, "rev-parse", "HEAD")
    remote_revision = _git_output(root, "ls-remote", "--heads", "origin", "main")
    if remote_revision:
        remote_revision = remote_revision.split()[0]
    return VersionCheck(
        local_version=__version__,
        local_revision=local_revision,
        remote_revision=remote_revision,
    )


def _agent_framework_label() -> str:
    explicit = _first_env("SKRYA_AGENT_FRAMEWORK", "AGENT_FRAMEWORK")
    explicit_version = _first_env("SKRYA_AGENT_VERSION", "AGENT_FRAMEWORK_VERSION")
    if explicit:
        return f"{explicit} {explicit_version}".strip()

    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_SESSION_ID"):
        codex_version = _first_env("CODEX_VERSION")
        return f"Codex {codex_version}".strip()

    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE"):
        claude_version = _first_env("CLAUDE_CODE_VERSION")
        return f"Claude Code {claude_version}".strip()

    if os.environ.get("OPENCLAW_WORKSPACE") or os.environ.get("OPENCLAW_CHANNEL_ID"):
        openclaw_version = _first_env("OPENCLAW_VERSION")
        return f"OpenClaw {openclaw_version}".strip()

    return ""


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _git_output(root: Path, *args: str) -> str | None:
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
