from __future__ import annotations

import argparse
from pathlib import Path

from .agent_assets import AssetBuilder
from .intelligence import IntelligenceService


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

    asset_parser = subparsers.add_parser("build-agent-assets")
    asset_parser.add_argument("--root", default=".", help="Workspace root")
    asset_parser.add_argument(
        "--host",
        default="workspace",
        choices=["workspace", "codex", "claude", "openclaw", "all"],
        help="Which host asset set to generate",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = IntelligenceService(Path(args.root))

    if args.command == "digest":
        result = service.generate_digest(args.topic)
        print(result.markdown, end="")
        return 0

    if args.command == "deep-analysis":
        result = service.generate_deep_analysis(args.topic, event_number=args.event_number)
        print(result.markdown, end="")
        return 0

    if args.command == "build-agent-assets":
        root = Path(args.root)
        AssetBuilder(root).build(output_root=root, host_name=args.host)
        print(f"Generated assets for host(s): {args.host}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

