from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import DataRootConfigResult, default_data_root_for_mode, write_data_root_config


PACK_METADATA_FILE = "skill-pack.json"
PACK_TEMPLATE_FILE = "SKILL.md.tmpl"
PROMPT_TEMPLATE_SUFFIX = ".md.tmpl"
RUNTIME_ARTIFACT_ROOT = ".skrya/hosts"
INSTALLER_ENTRY_DIR = "skrya"
SKILL_LINK_PREFIX = "skrya-"
INSTRUCTION_FILE_REFERENCE = "AGENTS.md, CLAUDE.md, or the equivalent repository instruction file"
COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".skrya", "tmp", "runs", ".venv")


@dataclass(frozen=True)
class SkillSource:
    name: str
    description: str
    display_name: str
    short_description: str
    default_prompt: str
    template_path: Path
    allow_implicit_invocation: bool = True

    @classmethod
    def from_metadata_file(cls, metadata_path: Path, template_path: Path) -> "SkillSource":
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return cls(
            name=metadata["name"],
            description=metadata["description"],
            display_name=metadata["display_name"],
            short_description=metadata["short_description"],
            default_prompt=metadata["default_prompt"],
            template_path=template_path,
            allow_implicit_invocation=metadata.get("allow_implicit_invocation", True),
        )


@dataclass(frozen=True)
class HostConfig:
    name: str
    instruction_file: str
    prompt_root: str
    global_skill_dir: str | None = None
    home_marker_dir: str | None = None
    default_data_root_mode: str = "home"

    @property
    def instruction_label(self) -> str:
        return self.instruction_file.rsplit(".", 1)[0]


HOSTS: dict[str, HostConfig] = {
    "workspace": HostConfig(
        name="workspace",
        instruction_file="AGENTS.md",
        prompt_root=f"{RUNTIME_ARTIFACT_ROOT}/workspace/prompts",
    ),
    "codex": HostConfig(
        name="codex",
        instruction_file="AGENTS.md",
        prompt_root=f"{RUNTIME_ARTIFACT_ROOT}/codex/prompts",
        global_skill_dir=".codex/skills/skrya",
        home_marker_dir=".codex",
    ),
    "claude": HostConfig(
        name="claude",
        instruction_file="CLAUDE.md",
        prompt_root=f"{RUNTIME_ARTIFACT_ROOT}/claude/prompts",
        global_skill_dir=".claude/skills/skrya",
        home_marker_dir=".claude",
    ),
    "openclaw": HostConfig(
        name="openclaw",
        instruction_file="AGENTS.md",
        prompt_root=f"{RUNTIME_ARTIFACT_ROOT}/openclaw/prompts",
        global_skill_dir=".openclaw/skills/skrya",
        home_marker_dir=".openclaw",
        default_data_root_mode="workspace",
    ),
}


@dataclass(frozen=True)
class InstallResult:
    host: str
    skill_name: str
    target_path: Path
    mode: str


@dataclass(frozen=True)
class UninstallResult:
    kind: str
    target_path: Path
    mode: str


class SkillPackBuilder:
    def __init__(self, template_root: Path | str) -> None:
        self._template_root = Path(template_root)

    def build(self, output_root: Path | str, host_name: str = "all") -> list[Path]:
        output_root = Path(output_root)
        written = self.build_runtime_pack(output_root)
        written.extend(self.build_host_prompts(output_root, host_name))
        return written

    def build_runtime_pack(self, output_root: Path | str) -> list[Path]:
        output_root = Path(output_root)
        written: list[Path] = []
        pack_source = self._load_pack_source()
        written.append(self._write_text(output_root / "SKILL.md", self._render_skill_markdown(pack_source)))
        written.append(
            self._write_text(output_root / "agents" / "openai.yaml", self._render_openai_metadata(pack_source))
        )
        written.extend(self._write_installer_entry(output_root, pack_source))

        for skill in self._load_skill_sources():
            skill_dir = output_root / skill.name
            written.append(self._write_text(skill_dir / "SKILL.md", self._render_skill_markdown(skill)))
            written.append(
                self._write_text(skill_dir / "agents" / "openai.yaml", self._render_openai_metadata(skill))
            )

        return written

    def _write_installer_entry(self, output_root: Path, pack_source: SkillSource) -> list[Path]:
        installer_root = output_root / INSTALLER_ENTRY_DIR
        return [
            self._write_text(installer_root / "SKILL.md", self._render_skill_markdown(pack_source)),
            self._write_text(
                installer_root / "agents" / "openai.yaml",
                self._render_openai_metadata(pack_source),
            ),
        ]

    def build_host_prompts(self, output_root: Path | str, host_name: str = "all") -> list[Path]:
        output_root = Path(output_root)
        written: list[Path] = []
        for host in self._resolve_hosts(host_name):
            prompt_root = output_root / host.prompt_root
            shutil.rmtree(prompt_root.parent, ignore_errors=True)
            for template_path in self._load_prompt_templates():
                prompt_name = template_path.name.removesuffix(PROMPT_TEMPLATE_SUFFIX)
                output_name = f"{prompt_name}-{host.instruction_label}.md"
                written.append(
                    self._write_text(
                        prompt_root / output_name,
                        self._render_host_template(template_path.read_text(encoding="utf-8"), host),
                    )
                )
        return written

    def _load_pack_source(self) -> SkillSource:
        return SkillSource.from_metadata_file(
            self._template_root / PACK_METADATA_FILE,
            self._template_root / PACK_TEMPLATE_FILE,
        )

    def _load_skill_sources(self) -> list[SkillSource]:
        sources: list[SkillSource] = []
        for path in sorted(self._template_root.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            metadata_path = path / "skill.json"
            template_path = path / PACK_TEMPLATE_FILE
            if metadata_path.exists() and template_path.exists():
                sources.append(SkillSource.from_metadata_file(metadata_path, template_path))
        return sources

    def _load_prompt_templates(self) -> list[Path]:
        prompt_root = self._template_root / "prompt-templates"
        return sorted(prompt_root.glob(f"*{PROMPT_TEMPLATE_SUFFIX}"))

    def _render_skill_markdown(self, skill: SkillSource) -> str:
        header = "\n".join(
            [
                "---",
                f"name: {skill.name}",
                f"description: {skill.description}",
                "---",
                "",
            ]
        )
        generated_from = skill.template_path.relative_to(self._template_root).as_posix()
        body = self._render_runtime_template(skill.template_path.read_text(encoding="utf-8"))
        return (
            f"{header}"
            f"<!-- AUTO-GENERATED from {generated_from}; regenerate with "
            f"`python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->\n\n"
            f"{body.rstrip()}\n"
        )

    @staticmethod
    def _render_openai_metadata(skill: SkillSource) -> str:
        return yaml.safe_dump(
            {
                "interface": {
                    "display_name": skill.display_name,
                    "short_description": skill.short_description,
                    "default_prompt": skill.default_prompt,
                },
                "policy": {
                    "allow_implicit_invocation": skill.allow_implicit_invocation,
                },
            },
            allow_unicode=True,
            sort_keys=False,
        )

    @staticmethod
    def _render_runtime_template(template: str) -> str:
        return (
            template.replace("{{INSTRUCTION_FILE}}", INSTRUCTION_FILE_REFERENCE)
            .replace("{{HOST_NAME}}", "workspace")
            .replace("{{SKILL_ROOT}}", "the repository root")
        )

    @staticmethod
    def _render_host_template(template: str, host: HostConfig) -> str:
        return (
            template.replace("{{HOST_NAME}}", host.name)
            .replace("{{INSTRUCTION_FILE}}", host.instruction_file)
            .replace("{{SKILL_ROOT}}", "the repository root")
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

    def _resolve_hosts(self, host_name: str) -> list[HostConfig]:
        return list(HOSTS.values()) if host_name == "all" else [self._resolve_host(host_name)]


class SkillPackInstaller:
    def __init__(self, template_root: Path | str) -> None:
        self._template_root = Path(template_root)
        self._builder = SkillPackBuilder(template_root)

    def install(self, output_root: Path | str, host_name: str = "auto") -> list[InstallResult]:
        output_root = Path(output_root).resolve()
        install_hosts = self._resolve_install_hosts(host_name)
        build_target = "all" if host_name == "auto" else host_name
        self._builder.build(output_root, build_target)

        results: list[InstallResult] = []
        for host in install_hosts:
            results.extend(self._install_host(output_root, host))
        return results

    def configure_data_roots(
        self,
        output_root: Path | str,
        host_name: str = "auto",
        *,
        mode: str = "host-default",
        custom_data_root: Path | str | None = None,
        config_scope: str | None = None,
        migrate: bool = False,
    ) -> list[DataRootConfigResult]:
        output_root = Path(output_root).resolve(strict=False)
        results: list[DataRootConfigResult] = []
        seen_configs: set[Path] = set()
        for host in self._resolve_install_hosts(host_name):
            host_mode = host.default_data_root_mode if mode == "host-default" else mode
            if host_mode == "none":
                continue
            if host_mode == "custom":
                if custom_data_root is None:
                    raise ValueError("--data-root-path is required when --data-root-mode custom")
                data_root = custom_data_root
                scope = config_scope or host.default_data_root_mode
                if scope not in {"home", "workspace"}:
                    raise ValueError(f"Unsupported data root config scope: {scope}")
            else:
                data_root = default_data_root_for_mode(host_mode)
                scope = host_mode

            result = write_data_root_config(output_root, data_root, scope=scope, migrate=migrate)
            if result.config_path in seen_configs:
                continue
            seen_configs.add(result.config_path)
            results.append(result)
        return results

    def uninstall(
        self,
        output_root: Path | str,
        host_name: str = "auto",
        *,
        mode: str = "skills-keep-data",
    ) -> list[UninstallResult]:
        output_root = Path(output_root).resolve(strict=False)
        if mode not in {"skills-keep-data", "data-keep-skills", "complete"}:
            raise ValueError(f"Unsupported uninstall mode: {mode}")

        results: list[UninstallResult] = []
        if mode in {"skills-keep-data", "complete"}:
            for host in self._resolve_install_hosts(host_name):
                results.extend(self._uninstall_host(host))

        if mode in {"data-keep-skills", "complete"}:
            results.extend(self._remove_data_root(output_root))

        if mode == "complete":
            for host in self._resolve_install_hosts(host_name):
                results.extend(self._remove_global_instruction_note(output_root, host))

        return results

    def _resolve_install_hosts(self, host_name: str) -> list[HostConfig]:
        if host_name != "auto":
            host = SkillPackBuilder._resolve_host(host_name)
            if host.global_skill_dir is None:
                raise ValueError(f"Host {host_name} does not support global installation")
            return [host]

        home = Path.home()
        detected = [
            host
            for host in HOSTS.values()
            if host.global_skill_dir is not None
            and host.home_marker_dir is not None
            and (home / host.home_marker_dir).exists()
        ]
        if detected:
            return detected
        return [HOSTS["codex"]]

    def _install_host(self, output_root: Path, host: HostConfig) -> list[InstallResult]:
        assert host.global_skill_dir is not None
        target = (Path.home() / host.global_skill_dir).resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)

        root_result = self._install_path(
            source=output_root,
            target=target,
            host=host.name,
            skill_name="skrya",
        )

        results = [root_result]
        for skill in self._builder._load_skill_sources():
            link_name = self._link_name(skill.name)
            skill_target = target.parent / link_name
            skill_source = target / skill.name
            results.append(
                self._install_path(
                    source=skill_source,
                    target=skill_target,
                    host=host.name,
                    skill_name=link_name,
                )
            )
        return results

    def _install_path(self, source: Path, target: Path, host: str, skill_name: str) -> InstallResult:
        if target.exists():
            try:
                if target.resolve() == source.resolve():
                    return InstallResult(host=host, skill_name=skill_name, target_path=target, mode="in-place")
            except OSError:
                pass
            raise FileExistsError(
                f"Refusing to overwrite existing install target for {host}/{skill_name}: {target}"
            )

        try:
            target.symlink_to(source, target_is_directory=True)
            return InstallResult(host=host, skill_name=skill_name, target_path=target, mode="symlink")
        except OSError:
            shutil.copytree(source, target, ignore=COPY_IGNORE)
            return InstallResult(host=host, skill_name=skill_name, target_path=target, mode="copy")

    @staticmethod
    def _link_name(skill_name: str) -> str:
        return f"{SKILL_LINK_PREFIX}{skill_name}"

    def _uninstall_host(self, host: HostConfig) -> list[UninstallResult]:
        assert host.global_skill_dir is not None
        target = (Path.home() / host.global_skill_dir).resolve(strict=False)
        paths = [target]
        for skill in self._builder._load_skill_sources():
            paths.append(target.parent / self._link_name(skill.name))

        results: list[UninstallResult] = []
        for path in paths:
            if not path.exists() and not path.is_symlink():
                continue
            self._remove_path(path)
            results.append(UninstallResult(kind="skill", target_path=path, mode="removed"))
        return results

    def _remove_data_root(self, output_root: Path) -> list[UninstallResult]:
        from .paths import CONFIG_RELATIVE_PATH, resolve_data_root

        resolution = resolve_data_root(output_root)
        results: list[UninstallResult] = []
        data_root = resolution.data_root
        if data_root.exists() or data_root.is_symlink():
            self._remove_path(data_root)
            results.append(UninstallResult(kind="data-root", target_path=data_root, mode="removed"))

        config_candidates = [
            output_root / CONFIG_RELATIVE_PATH,
            Path.home() / CONFIG_RELATIVE_PATH,
        ]
        if resolution.config_path:
            config_candidates.append(resolution.config_path)
        seen: set[Path] = set()
        for path in config_candidates:
            path = path.resolve(strict=False)
            if path in seen:
                continue
            seen.add(path)
            if not path.exists():
                continue
            try:
                payload = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "data_root" not in payload:
                continue
            path.unlink()
            results.append(UninstallResult(kind="data-config", target_path=path, mode="removed"))
        return results

    def _remove_global_instruction_note(self, output_root: Path, host: HostConfig) -> list[UninstallResult]:
        candidates = [
            output_root / host.instruction_file,
            Path.home() / host.instruction_file,
        ]
        if host.home_marker_dir:
            candidates.append(Path.home() / host.home_marker_dir / host.instruction_file)

        results: list[UninstallResult] = []
        seen: set[Path] = set()
        for path in candidates:
            path = path.resolve(strict=False)
            if path in seen or not path.exists():
                continue
            seen.add(path)
            original = path.read_text(encoding="utf-8")
            updated = self._strip_skrya_instruction_blocks(original)
            if updated == original:
                continue
            path.write_text(updated, encoding="utf-8")
            results.append(UninstallResult(kind="global-instruction", target_path=path, mode="skrya-note-removed"))
        return results

    @staticmethod
    def _strip_skrya_instruction_blocks(content: str) -> str:
        start = "<!-- SKRYA-ROUTING-NOTE:START -->"
        end = "<!-- SKRYA-ROUTING-NOTE:END -->"
        while start in content and end in content:
            start_index = content.index(start)
            end_index = content.index(end, start_index) + len(end)
            if end_index < len(content) and content[end_index : end_index + 1] == "\n":
                end_index += 1
            content = content[:start_index] + content[end_index:]
        return content

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return
        shutil.rmtree(path)
