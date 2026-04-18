from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SkillSource:
    name: str
    description: str
    display_name: str
    short_description: str
    default_prompt: str
    template_path: Path

    @classmethod
    def from_dir(cls, skill_dir: Path) -> "SkillSource":
        metadata = json.loads((skill_dir / "skill.json").read_text(encoding="utf-8"))
        return cls(
            name=metadata["name"],
            description=metadata["description"],
            display_name=metadata["display_name"],
            short_description=metadata["short_description"],
            default_prompt=metadata["default_prompt"],
            template_path=skill_dir / "SKILL.md.tmpl",
        )


@dataclass(frozen=True)
class HostConfig:
    name: str
    skill_root: str
    instruction_file: str
    prompt_root: str
    generate_openai_metadata: bool

    @property
    def instruction_label(self) -> str:
        return self.instruction_file.rsplit(".", 1)[0]


HOSTS: dict[str, HostConfig] = {
    "workspace": HostConfig(
        name="workspace",
        skill_root="skills",
        instruction_file="AGENTS.md",
        prompt_root="agent-hosts/workspace",
        generate_openai_metadata=True,
    ),
    "codex": HostConfig(
        name="codex",
        skill_root=".agents/skills",
        instruction_file="AGENTS.md",
        prompt_root="agent-hosts/codex",
        generate_openai_metadata=True,
    ),
    "claude": HostConfig(
        name="claude",
        skill_root=".claude/skills",
        instruction_file="CLAUDE.md",
        prompt_root="agent-hosts/claude",
        generate_openai_metadata=False,
    ),
    "openclaw": HostConfig(
        name="openclaw",
        skill_root=".openclaw/skills",
        instruction_file="AGENTS.md",
        prompt_root="agent-hosts/openclaw",
        generate_openai_metadata=False,
    ),
}


class AssetBuilder:
    def __init__(self, template_root: Path | str) -> None:
        self._template_root = Path(template_root)

    def build(self, output_root: Path | str, host_name: str = "workspace") -> list[Path]:
        output_root = Path(output_root)
        host_names = list(HOSTS) if host_name == "all" else [host_name]
        written: list[Path] = []

        for current_host_name in host_names:
            host = self._resolve_host(current_host_name)
            written.extend(self._build_host(output_root, host))

        return written

    def _build_host(self, output_root: Path, host: HostConfig) -> list[Path]:
        written: list[Path] = []

        for skill in self._load_skill_sources():
            skill_dir = output_root / host.skill_root / skill.name
            written.append(
                self._write_text(
                    skill_dir / "SKILL.md",
                    self._render_skill_markdown(skill, host),
                )
            )
            if host.generate_openai_metadata:
                written.append(
                    self._write_text(
                        skill_dir / "agents" / "openai.yaml",
                        self._render_openai_metadata(skill),
                    )
                )

        for template_path in self._load_prompt_templates():
            prompt_name = template_path.name.removesuffix(".md.tmpl")
            output_name = f"{prompt_name}-{host.instruction_label}.md"
            written.append(
                self._write_text(
                    output_root / host.prompt_root / output_name,
                    self._render_template(template_path.read_text(encoding="utf-8"), host),
                )
            )

        return written

    def _load_skill_sources(self) -> list[SkillSource]:
        source_root = self._template_root / "skills-src"
        return [
            SkillSource.from_dir(skill_dir)
            for skill_dir in sorted(path for path in source_root.iterdir() if path.is_dir())
        ]

    def _load_prompt_templates(self) -> list[Path]:
        prompt_root = self._template_root / "prompt-templates"
        return sorted(prompt_root.glob("*.md.tmpl"))

    def _render_skill_markdown(self, skill: SkillSource, host: HostConfig) -> str:
        header = "\n".join(
            [
                "---",
                f"name: {skill.name}",
                f"description: {skill.description}",
                "---",
                "",
            ]
        )
        body = self._render_template(skill.template_path.read_text(encoding="utf-8"), host)
        return f"{header}{body.rstrip()}\n"

    @staticmethod
    def _render_openai_metadata(skill: SkillSource) -> str:
        return yaml.safe_dump(
            {
                "display_name": skill.display_name,
                "short_description": skill.short_description,
                "default_prompt": skill.default_prompt,
            },
            allow_unicode=True,
            sort_keys=False,
        )

    @staticmethod
    def _render_template(template: str, host: HostConfig) -> str:
        return (
            template.replace("{{HOST_NAME}}", host.name)
            .replace("{{INSTRUCTION_FILE}}", host.instruction_file)
            .replace("{{SKILL_ROOT}}", host.skill_root)
        )

    @staticmethod
    def _write_text(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def _resolve_host(host_name: str) -> HostConfig:
        try:
            return HOSTS[host_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported host: {host_name}") from exc
