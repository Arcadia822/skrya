from __future__ import annotations

import argparse
from pathlib import Path

from .agent_assets import SkillPackBuilder, SkillPackInstaller
from .intelligence import IntelligenceService


BUILD_HOST_CHOICES = ["workspace", "codex", "claude", "openclaw", "all"]
INSTALL_HOST_CHOICES = ["auto", "codex", "claude", "openclaw"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skrya topic-driven briefing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--topic", required=True, help="Topic id")
    digest_parser.add_argument("--root", default=".", help="Workspace root")

    analysis_parser = subparsers.add_parser("deep-analysis")
    analysis_parser.add_argument("--topic", required=True, help="Topic id")
    analysis_parser.add_argument("--event-number", required=True, type=int, help="Visible digest event number")
    analysis_parser.add_argument("--root", default=".", help="Workspace root")

    build_parser = subparsers.add_parser("build-skill-pack")
    build_parser.add_argument("--root", default=".", help="Workspace root")
    build_parser.add_argument(
        "--host",
        default="all",
        choices=BUILD_HOST_CHOICES,
        help="Which host prompt packs to generate",
    )

    legacy_build_parser = subparsers.add_parser("build-agent-assets")
    legacy_build_parser.add_argument("--root", default=".", help="Workspace root")
    legacy_build_parser.add_argument(
        "--host",
        default="all",
        choices=BUILD_HOST_CHOICES,
        help="Backward-compatible alias for build-skill-pack",
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
        result = service.generate_digest(args.topic)
        print(result.markdown, end="")
        return 0

    if args.command == "deep-analysis":
        result = service.generate_deep_analysis(args.topic, event_number=args.event_number)
        print(result.markdown, end="")
        return 0

    if args.command in {"build-skill-pack", "build-agent-assets"}:
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
