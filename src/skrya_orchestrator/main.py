from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_assets import SkillPackBuilder, SkillPackInstaller
from .ingest import IngestService
from .intelligence import IntelligenceService
from .paths import migrate_workspace_data, resolve_data_root, write_data_root_config


BUILD_HOST_CHOICES = ["workspace", "codex", "claude", "openclaw", "all"]
INSTALL_HOST_CHOICES = ["auto", "codex", "claude", "openclaw"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skrya topic-driven briefing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--topic", required=True, help="Topic id")
    digest_parser.add_argument("--root", default=".", help="Workspace root")
    digest_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    digest_parser.add_argument("--sample", action="store_true", help="Use sample-events.json even when live sources exist")

    analysis_parser = subparsers.add_parser("deep-analysis")
    analysis_parser.add_argument("--topic", required=True, help="Topic id")
    analysis_parser.add_argument("--event-number", required=True, type=int, help="Visible digest event number")
    analysis_parser.add_argument("--root", default=".", help="Workspace root")
    analysis_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    event_thread_parser = subparsers.add_parser("event-thread")
    event_thread_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    event_thread_parser.add_argument("--thread", required=True, help="Event-thread id or visible name")
    event_thread_parser.add_argument("--root", default=".", help="Workspace root")
    event_thread_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    refresh_event_threads_parser = subparsers.add_parser("refresh-event-threads")
    refresh_event_threads_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    refresh_event_threads_parser.add_argument("--root", default=".", help="Workspace root")
    refresh_event_threads_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    retrieval_parser = subparsers.add_parser("retrieval-request")
    retrieval_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    retrieval_parser.add_argument("--root", default=".", help="Workspace root")
    retrieval_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    retrieval_parser.add_argument("--since", default=None, help="Optional ISO lower bound")
    retrieval_parser.add_argument("--until", default=None, help="Optional ISO upper bound")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    ingest_parser.add_argument("--root", default=".", help="Workspace root")
    ingest_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    ingest_parser.add_argument("--file", required=True, help="Path to skrya.ingest.v1 JSON")
    ingest_parser.add_argument("--raw-file", default=None, help="Optional raw provider output file")

    data_root_parser = subparsers.add_parser("data-root")
    data_root_parser.add_argument("--root", default=".", help="Workspace root")
    data_root_parser.add_argument("--set", dest="set_data_root", default=None, help="Persist a Skrya data root")
    data_root_parser.add_argument(
        "--scope",
        default="home",
        choices=["home", "workspace"],
        help="Where to save the data-root config",
    )
    data_root_parser.add_argument("--migrate", action="store_true", help="Copy existing workspace topics/runs")

    build_parser = subparsers.add_parser("build-skill-pack")
    build_parser.add_argument("--root", default=".", help="Workspace root")
    build_parser.add_argument(
        "--host",
        default="all",
        choices=BUILD_HOST_CHOICES,
        help="Which host prompt packs to generate",
    )

    install_parser = subparsers.add_parser("install-skill-pack")
    install_parser.add_argument("--root", default=".", help="Workspace root")
    install_parser.add_argument(
        "--host",
        default="auto",
        choices=INSTALL_HOST_CHOICES,
        help="Which host to install globally",
    )
    install_parser.add_argument(
        "--data-root-mode",
        default="host-default",
        choices=["host-default", "home", "workspace", "custom", "none"],
        help="Where installed skills should store topics/runs",
    )
    install_parser.add_argument("--data-root-path", default=None, help="Custom data root when mode is custom")
    install_parser.add_argument(
        "--data-root-config-scope",
        default=None,
        choices=["home", "workspace"],
        help="Where to write the data-root config when using a custom path",
    )
    install_parser.add_argument("--migrate-data", action="store_true", help="Copy existing workspace topics/runs")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root)

    if args.command == "digest":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.generate_digest(args.topic, prefer_live=not args.sample)
        print(result.markdown, end="")
        return 0

    if args.command == "deep-analysis":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.generate_deep_analysis(args.topic, event_number=args.event_number)
        print(result.markdown, end="")
        return 0

    if args.command == "event-thread":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.generate_event_thread_timeline(args.topic, thread_reference=args.thread)
        print(result.markdown, end="")
        return 0

    if args.command == "refresh-event-threads":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.refresh_event_threads(args.topic)
        print(f"Refreshed event threads: {result.artifact_path}")
        return 0

    if args.command == "retrieval-request":
        request = IngestService(root, data_root=args.data_root).build_retrieval_request(
            args.topic,
            since=args.since,
            until=args.until,
        )
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        raw_text = Path(args.raw_file).read_text(encoding="utf-8") if args.raw_file else None
        result = IngestService(root, data_root=args.data_root).record_ingest_result(args.topic, payload, raw_text=raw_text)
        print(f"Recorded ingest: {result.latest_path}")
        return 0

    if args.command == "data-root":
        if args.set_data_root:
            result = write_data_root_config(root, args.set_data_root, scope=args.scope, migrate=args.migrate)
            print(f"Configured Skrya data root: {result.data_root}")
            print(f"Config file: {result.config_path}")
            if result.migrated:
                print("Migrated:")
                for path in result.migrated:
                    print(f"- {path}")
            return 0

        resolution = resolve_data_root(root)
        print(f"Skrya data root: {resolution.data_root}")
        print(f"Source: {resolution.source}")
        if resolution.config_path:
            print(f"Config file: {resolution.config_path}")
        if args.migrate:
            migrated = migrate_workspace_data(root, resolution.data_root)
            if migrated:
                print("Migrated:")
                for path in migrated:
                    print(f"- {path}")
        return 0

    if args.command == "build-skill-pack":
        SkillPackBuilder(root).build(output_root=root, host_name=args.host)
        print(f"Generated skill pack artifacts for host(s): {args.host}")
        return 0

    if args.command == "install-skill-pack":
        installer = SkillPackInstaller(root)
        results = installer.install(output_root=root, host_name=args.host)
        for result in results:
            print(f"{result.host}/{result.skill_name}: {result.mode} -> {result.target_path}")
        config_results = installer.configure_data_roots(
            output_root=root,
            host_name=args.host,
            mode=args.data_root_mode,
            custom_data_root=args.data_root_path,
            config_scope=args.data_root_config_scope,
            migrate=args.migrate_data,
        )
        for result in config_results:
            print(f"data-root: {result.data_root} (config: {result.config_path})")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
