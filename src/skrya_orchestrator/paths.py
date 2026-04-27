from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


CONFIG_RELATIVE_PATH = Path(".skrya") / "config.json"
ENV_DATA_ROOT = "SKRYA_DATA_ROOT"
DEFAULT_HOME_DATA_ROOT = "~/.skrya"
DEFAULT_WORKSPACE_DATA_ROOT = ".skrya/data"

DataRootScope = Literal["home", "workspace"]


@dataclass(frozen=True)
class DataRootResolution:
    data_root: Path
    source: str
    config_path: Path | None = None


@dataclass(frozen=True)
class DataRootConfigResult:
    data_root: Path
    config_path: Path
    migrated: list[Path]


def resolve_data_root(workspace_root: Path | str, explicit_data_root: Path | str | None = None) -> DataRootResolution:
    workspace_root = Path(workspace_root).resolve(strict=False)
    if explicit_data_root is not None:
        return DataRootResolution(
            data_root=_expand_data_root(str(explicit_data_root), base=workspace_root),
            source="explicit",
        )

    env_value = os.environ.get(ENV_DATA_ROOT)
    if env_value:
        return DataRootResolution(
            data_root=_expand_data_root(env_value, base=workspace_root),
            source=ENV_DATA_ROOT,
        )

    workspace_config = workspace_root / CONFIG_RELATIVE_PATH
    configured = _read_configured_data_root(workspace_config, base=workspace_root)
    if configured is not None:
        return DataRootResolution(data_root=configured, source="workspace-config", config_path=workspace_config)

    home = Path.home().resolve(strict=False)
    home_config = home / CONFIG_RELATIVE_PATH
    configured = _read_configured_data_root(home_config, base=home)
    if configured is not None:
        return DataRootResolution(data_root=configured, source="home-config", config_path=home_config)

    return DataRootResolution(
        data_root=_expand_data_root(DEFAULT_HOME_DATA_ROOT, base=home),
        source="default-home",
    )


def default_data_root_for_mode(mode: str) -> str:
    if mode == "home":
        return DEFAULT_HOME_DATA_ROOT
    if mode == "workspace":
        return DEFAULT_WORKSPACE_DATA_ROOT
    raise ValueError(f"Unsupported data root mode: {mode}")


def write_data_root_config(
    workspace_root: Path | str,
    data_root: Path | str,
    *,
    scope: DataRootScope,
    migrate: bool = False,
) -> DataRootConfigResult:
    workspace_root = Path(workspace_root).resolve(strict=False)
    if scope == "home":
        base = Path.home().resolve(strict=False)
        config_path = base / CONFIG_RELATIVE_PATH
    elif scope == "workspace":
        base = workspace_root
        config_path = workspace_root / CONFIG_RELATIVE_PATH
    else:
        raise ValueError(f"Unsupported data root config scope: {scope}")

    data_root_text = str(data_root)
    resolved_data_root = _expand_data_root(data_root_text, base=base)
    resolved_data_root.mkdir(parents=True, exist_ok=True)
    (resolved_data_root / "topics").mkdir(parents=True, exist_ok=True)
    (resolved_data_root / "runs").mkdir(parents=True, exist_ok=True)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data_root": data_root_text,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    migrated = migrate_workspace_data(workspace_root, resolved_data_root) if migrate else []
    return DataRootConfigResult(data_root=resolved_data_root, config_path=config_path, migrated=migrated)


def migrate_workspace_data(workspace_root: Path | str, data_root: Path | str) -> list[Path]:
    workspace_root = Path(workspace_root).resolve(strict=False)
    data_root = Path(data_root).resolve(strict=False)
    migrated: list[Path] = []
    for dirname in ("topics", "runs"):
        source = workspace_root / dirname
        target = data_root / dirname
        if not source.exists():
            continue
        _copy_missing_tree(source, target)
        migrated.append(target)
    return migrated


def migrate_thread_naming(data_root: Path | str) -> list[Path]:
    data_root = Path(data_root).resolve(strict=False)
    migrated: list[Path] = []

    topics_root = data_root / "topics"
    if topics_root.exists():
        for topic_dir in topics_root.iterdir():
            if not topic_dir.is_dir():
                continue
            migrated.extend(
                _migrate_json_file(
                    topic_dir / "event-thread-seeds.json",
                    topic_dir / "thread-seeds.json",
                )
            )

    runs_root = data_root / "runs"
    if runs_root.exists():
        for run_dir in runs_root.iterdir():
            if not run_dir.is_dir():
                continue
            migrated.extend(
                _migrate_json_file(
                    run_dir / "event-threads" / "latest-event-threads.json",
                    run_dir / "threads" / "latest-threads.json",
                )
            )

    return migrated


def _read_configured_data_root(config_path: Path, *, base: Path) -> Path | None:
    if not config_path.exists():
        return None
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    data_root = str(payload.get("data_root", "")).strip()
    if not data_root:
        raise ValueError(f"Missing data_root in Skrya config: {config_path}")
    return _expand_data_root(data_root, base=base)


def _expand_data_root(value: str, *, base: Path) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if not expanded.is_absolute():
        expanded = base / expanded
    return expanded.resolve(strict=False)


def _copy_missing_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.rglob("*"):
        relative = source_path.relative_to(source)
        target_path = target / relative
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        if target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def _migrate_json_file(source: Path, target: Path) -> list[Path]:
    if not source.exists() or target.exists():
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        shutil.copy2(source, target)
    else:
        target.write_text(
            json.dumps(_rename_thread_terms(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return [target]


def _rename_thread_terms(value):
    if isinstance(value, dict):
        renamed = {}
        for key, item in value.items():
            new_key = _rename_thread_text(str(key))
            if new_key == "event_threads":
                new_key = "threads"
            renamed[new_key] = _rename_thread_terms(item)
        return renamed
    if isinstance(value, list):
        return [_rename_thread_terms(item) for item in value]
    if isinstance(value, str):
        return _rename_thread_text(value)
    return value


def _rename_thread_text(value: str) -> str:
    return (
        value.replace("event-thread-seeds", "thread-seeds")
        .replace("event-threads", "threads")
        .replace("event-thread", "thread")
        .replace("event_thread", "thread")
        .replace("EventThread", "Thread")
    )
