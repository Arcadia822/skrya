from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_assets import SkillPackBuilder, SkillPackInstaller
from .ingest import IngestService
from .intelligence import IntelligenceService


BUILD_HOST_CHOICES = ["workspace", "codex", "claude", "openclaw", "all"]
INSTALL_HOST_CHOICES = ["auto", "codex", "claude", "openclaw"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skrya topic-driven briefing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--topic", required=True, help="Topic id")
    digest_parser.add_argument("--root", default=".", help="Workspace root")
    digest_parser.add_argument("--sample", action="store_true", help="Use sample-events.json even when live sources exist")

    analysis_parser = subparsers.add_parser("deep-analysis")
    analysis_parser.add_argument("--topic", required=True, help="Topic id")
    analysis_parser.add_argument("--event-number", required=True, type=int, help="Visible digest event number")
    analysis_parser.add_argument("--root", default=".", help="Workspace root")

    event_thread_parser = subparsers.add_parser("event-thread")
    event_thread_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    event_thread_parser.add_argument("--thread", required=True, help="Event-thread id or visible name")
    event_thread_parser.add_argument("--root", default=".", help="Workspace root")

    refresh_event_threads_parser = subparsers.add_parser("refresh-event-threads")
    refresh_event_threads_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    refresh_event_threads_parser.add_argument("--root", default=".", help="Workspace root")

    retrieval_parser = subparsers.add_parser("retrieval-request")
    retrieval_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    retrieval_parser.add_argument("--root", default=".", help="Workspace root")
    retrieval_parser.add_argument("--since", default=None, help="Optional ISO lower bound")
    retrieval_parser.add_argument("--until", default=None, help="Optional ISO upper bound")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    ingest_parser.add_argument("--root", default=".", help="Workspace root")
    ingest_parser.add_argument("--file", required=True, help="Path to skrya.ingest.v1 JSON")
    ingest_parser.add_argument("--raw-file", default=None, help="Optional raw provider output file")

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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root)
    service = IntelligenceService(root)

    if args.command == "digest":
        result = service.generate_digest(args.topic, prefer_live=not args.sample)
        print(result.markdown, end="")
        return 0

    if args.command == "deep-analysis":
        result = service.generate_deep_analysis(args.topic, event_number=args.event_number)
        print(result.markdown, end="")
        return 0

    if args.command == "event-thread":
        result = service.generate_event_thread_timeline(args.topic, thread_reference=args.thread)
        print(result.markdown, end="")
        return 0

    if args.command == "refresh-event-threads":
        result = service.refresh_event_threads(args.topic)
        print(f"Refreshed event threads: {result.artifact_path}")
        return 0

    if args.command == "retrieval-request":
        request = IngestService(root).build_retrieval_request(args.topic, since=args.since, until=args.until)
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        raw_text = Path(args.raw_file).read_text(encoding="utf-8") if args.raw_file else None
        result = IngestService(root).record_ingest_result(args.topic, payload, raw_text=raw_text)
        print(f"Recorded ingest: {result.latest_path}")
        return 0

    if args.command == "build-skill-pack":
        SkillPackBuilder(root).build(output_root=root, host_name=args.host)
        print(f"Generated skill pack artifacts for host(s): {args.host}")
        return 0

    if args.command == "install-skill-pack":
        results = SkillPackInstaller(root).install(output_root=root, host_name=args.host)
        for result in results:
            print(f"{result.host}/{result.skill_name}: {result.mode} -> {result.target_path}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
