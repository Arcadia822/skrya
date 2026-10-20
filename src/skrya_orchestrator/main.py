from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent_assets import SkillPackBuilder, SkillPackInstaller
from .ingest import IngestService
from .intelligence import IntelligenceService
from .paths import migrate_thread_naming, migrate_workspace_data, resolve_data_root, write_data_root_config
from .template_validation import validate_digest_template
from .version import check_latest_version


BUILD_HOST_CHOICES = ["workspace", "codex", "claude", "openclaw", "all"]
INSTALL_HOST_CHOICES = ["auto", "codex", "claude", "openclaw"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Skrya topic-driven briefing CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    card_parser = subparsers.add_parser("render-card", help="Render Markdown as a lossless Feishu card bundle")
    card_parser.add_argument("--file", required=True, help="Complete Markdown digest file")
    card_parser.add_argument("--format", choices=["feishu-v2"], default="feishu-v2")
    card_parser.add_argument("-o", "--output", required=True, help="Output card-bundle JSON file")
    card_parser.add_argument("--root", default=".", help="Workspace root")

    reference_parser = subparsers.add_parser("resolve-reference", help="Resolve a reference against a frozen digest")
    reference_parser.add_argument("--topic", required=True)
    reference_parser.add_argument("--reference", required=True, help="N-xx or T-xx")
    reference_source = reference_parser.add_mutually_exclusive_group(required=True)
    reference_source.add_argument("--artifact", help="Timestamped digest Markdown or latest pointer")
    reference_source.add_argument("--binding", help="Delivery binding ID")
    reference_parser.add_argument("--message-id", help="Received message ID; requires --binding")
    reference_parser.add_argument("--root", default=".")
    reference_parser.add_argument("--data-root", default=None)
    for command in ("deliver", "delivery-check"):
        delivery_parser = subparsers.add_parser(command, help="Send a bound digest" if command == "deliver" else "Check delivery without sending")
        delivery_parser.add_argument("--channel", choices=["feishu"], required=True)
        delivery_parser.add_argument("--topic", required=True)
        delivery_parser.add_argument("--target", required=True, help="Explicit bound chat, user or configured alias")
        delivery_parser.add_argument("--binding", default=None, help="Select one binding when multiple match")
        delivery_parser.add_argument("--root", default=".")
        delivery_parser.add_argument("--data-root", default=None)
        if command == "deliver":
            delivery_parser.add_argument("--file", required=True, help="Complete digest Markdown with its frozen index")
            delivery_parser.add_argument("--layout", choices=["full-card", "summary+thread"], default=None)


    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--topic", required=True, help="Topic id")
    digest_parser.add_argument("--root", default=".", help="Workspace root")
    digest_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    digest_parser.add_argument("--sample", action="store_true", help="Use sample-events.json even when live sources exist")
    preview_group = digest_parser.add_mutually_exclusive_group()
    preview_group.add_argument("--preview", action="store_true", help="Preview digest output without writing artifacts")
    preview_group.add_argument("--test-run", action="store_true", help="Alias for --preview")
    digest_parser.add_argument("--force-refresh", action="store_true", help="Bypass HTTP cache freshness for live source collection")

    analysis_parser = subparsers.add_parser("deep-analysis")
    analysis_parser.add_argument("--topic", required=True, help="Topic id")
    analysis_parser.add_argument("--event-number", required=True, type=int, help="Visible digest event number")
    analysis_parser.add_argument("--root", default=".", help="Workspace root")
    analysis_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    thread_parser = subparsers.add_parser("thread")
    thread_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    thread_parser.add_argument("--thread", required=True, help="Thread id or visible name")
    thread_parser.add_argument("--root", default=".", help="Workspace root")
    thread_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    refresh_threads_parser = subparsers.add_parser("refresh-threads")
    refresh_threads_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    refresh_threads_parser.add_argument("--root", default=".", help="Workspace root")
    refresh_threads_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")

    validate_template_parser = subparsers.add_parser("validate-digest-template")
    validate_template_parser.add_argument("--file", required=True, help="Candidate digest template file")
    validate_template_parser.add_argument("--root", default=".", help="Workspace root")

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
    ingest_parser.add_argument("--file", required=True, help="Path to skrya.ingest.v2 JSON")
    ingest_parser.add_argument("--raw-file", default=None, help="Optional raw provider output file")


    cache_parser = subparsers.add_parser("cache", help="Maintain Skrya HTTP and translation caches")
    cache_parser.add_argument("--root", default=".", help="Workspace root")
    cache_parser.add_argument("--data-root", default=None, help="Skrya data root holding cache subtrees")
    cache_parser.add_argument("--clear-http-cache", action="store_true", help="Remove recognized HTTP cache entries")
    cache_parser.add_argument(
        "--clear-translation-cache",
        action="store_true",
        help="Remove recognized translation cache entries, optionally scoped by --translation-language",
    )
    cache_parser.add_argument(
        "--translation-language",
        default=None,
        help="Optional language scope for --clear-translation-cache (for example zh-CN or en)",
    )
    cache_parser.add_argument("--cleanup-expired", action="store_true", help="Remove HTTP cache entries past the expiry grace window")

    source_health_parser = subparsers.add_parser("source-health", help="Report topic source health")
    source_health_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    source_health_parser.add_argument("--root", default=".", help="Workspace root")
    source_health_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    source_health_parser.add_argument("--refresh", action="store_true", help="Refresh health via one live collection for the explicit topic")
    source_health_parser.add_argument("--force-refresh", action="store_true", help="Implies --refresh and bypasses HTTP cache freshness")

    ingest_prune_parser = subparsers.add_parser("ingest-prune", help="Prune archived ingest batches for a topic")
    ingest_prune_parser.add_argument("--topic", required=True, help="Topic id or topic name")
    ingest_prune_parser.add_argument("--root", default=".", help="Workspace root")
    ingest_prune_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    ingest_prune_parser.add_argument("--keep", type=int, default=10, help="Number of newest ingest batches to keep (default 10)")
    ingest_prune_parser.add_argument("--apply", action="store_true", help="Delete selected batches; without this flag the command only reports")

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

    uninstall_parser = subparsers.add_parser("uninstall-skill-pack")
    uninstall_parser.add_argument("--root", default=".", help="Workspace root")
    uninstall_parser.add_argument(
        "--host",
        default="auto",
        choices=INSTALL_HOST_CHOICES,
        help="Which host to uninstall globally",
    )
    uninstall_parser.add_argument(
        "--mode",
        default="skills-keep-data",
        choices=["skills-keep-data", "data-keep-skills", "complete"],
        help="Uninstall mode",
    )

    version_parser = subparsers.add_parser("version")
    version_parser.add_argument("--root", default=".", help="Workspace root")
    version_parser.add_argument("--check-latest", action="store_true", help="Check visible upstream revision")

    upgrade_parser = subparsers.add_parser("upgrade")
    upgrade_parser.add_argument("--root", default=".", help="Workspace root")
    upgrade_parser.add_argument("--data-root", default=None, help="Skrya data root for topics and runs")
    upgrade_parser.add_argument("--migrate-data", action="store_true", help="Copy existing workspace topics/runs")
    upgrade_parser.add_argument("--migrate-thread-naming", action="store_true", help="Migrate legacy thread file names")
    upgrade_parser.add_argument("--check-latest", action="store_true", help="Check visible upstream revision")
    upgrade_parser.add_argument("--topic", default=None, help="Optional topic id or name scoped to --migrate-ingest-v2")
    upgrade_parser.add_argument("--migrate-ingest-v2", action="store_true", help="Migrate current latest-ingest files from skrya.ingest.v1 to v2 with backups")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root)

    if args.command == "render-card":
        from .feishu_cards import render_card_bundle

        try:
            bundle = render_card_bundle(Path(args.file).read_text(encoding="utf-8"))
            output_path = Path(args.output)
            if output_path.resolve() == Path(args.file).resolve():
                raise ValueError("Card output must not overwrite the Markdown digest")
            output_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Rendered {len(bundle['cards'])} card(s): {output_path}")
            return 0
        except (OSError, ValueError) as error:
            print(f"Render failed: {error}", file=sys.stderr)
            return 1

    if args.command in {"deliver", "delivery-check", "resolve-reference"}:
        from .feishu_delivery import FeishuDeliveryService
        from .references import load_snapshot, resolve_reference

        try:
            service = IntelligenceService(root, data_root=args.data_root)
            topic_id = service.resolve_topic_id(args.topic)
            if Path(topic_id).name != topic_id or topic_id in {".", ".."}:
                raise ValueError("Topic ID must name one topic directory")
            data_root = resolve_data_root(root, args.data_root).data_root
            delivery = FeishuDeliveryService(data_root)
            if args.command == "resolve-reference":
                if args.message_id and not args.binding:
                    raise ValueError("--message-id requires --binding")
                if args.artifact:
                    artifact = Path(args.artifact).resolve()
                    if not artifact.is_relative_to((data_root / "runs" / topic_id).resolve()):
                        raise ValueError("Artifact does not belong to the resolved topic")
                    snapshot = load_snapshot(artifact)
                else:
                    snapshot = delivery.load_snapshot(topic_id, args.binding, message_id=args.message_id)
                if snapshot.get("topic_id") != topic_id:
                    raise ValueError("Snapshot does not belong to the resolved topic")
                result = resolve_reference(snapshot, args.reference)
            elif args.command == "delivery-check":
                result = delivery.check(topic_id, args.target, binding_id=args.binding)
            else:
                result = delivery.deliver(topic_id, Path(args.file), args.target, binding_id=args.binding, layout=args.layout)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("state") not in {"failed", "partial", "unknown"} else 1
        except (OSError, ValueError, RuntimeError) as error:
            print(f"{args.command} failed: {error}", file=sys.stderr)
            return 1



    if args.command == "digest":
        service = IntelligenceService(root, data_root=args.data_root)
        is_preview = getattr(args, "preview", False) or getattr(args, "test_run", False)
        try:
            result = service.generate_digest(
                args.topic, prefer_live=not args.sample, preview=is_preview, force_refresh=args.force_refresh
            )
        except (OSError, ValueError) as error:
            print(f"Digest failed: {error}", file=sys.stderr)
            return 1
        print(result.markdown, end="")
        return 0

    if args.command == "deep-analysis":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.generate_deep_analysis(args.topic, event_number=args.event_number)
        print(result.markdown, end="")
        return 0

    if args.command == "thread":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.generate_thread_timeline(args.topic, thread_reference=args.thread)
        print(result.markdown, end="")
        return 0

    if args.command == "refresh-threads":
        service = IntelligenceService(root, data_root=args.data_root)
        result = service.refresh_threads(args.topic)
        print(f"Refreshed threads: {result.artifact_path}")
        return 0

    if args.command == "validate-digest-template":
        template_path = Path(args.file)
        result = validate_digest_template(template_path.read_text(encoding="utf-8"))
        if result.valid:
            print(f"Digest template valid: {template_path}")
            return 0
        print(f"Digest template invalid: {template_path}")
        for issue in result.issues:
            print(f"- {issue.code}: {issue.message}")
        return 1

    if args.command == "retrieval-request":
        from .source_collector import with_source_fallbacks

        request = IngestService(root, data_root=args.data_root).build_retrieval_request(
            args.topic,
            since=args.since,
            until=args.until,
        )
        service = IntelligenceService(root, data_root=args.data_root)
        request = with_source_fallbacks(request, fallbacks=service.pending_source_fallbacks(args.topic))
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest":
        try:
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            raw_text = Path(args.raw_file).read_text(encoding="utf-8") if args.raw_file else None
            result = IngestService(root, data_root=args.data_root).record_ingest_result(args.topic, payload, raw_text=raw_text)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Record ingest failed: {error}", file=sys.stderr)
            return 1
        print(f"Recorded ingest: {result.latest_path}")
        return 0

    if args.command == "cache":
        from .http_cache import HttpCache
        from .translation_cache import TranslationCache

        if not (args.clear_http_cache or args.clear_translation_cache or args.cleanup_expired):
            print(
                "No cache action requested. Use --clear-http-cache, --clear-translation-cache "
                "[--translation-language zh-CN|en] or --cleanup-expired.",
                file=sys.stderr,
            )
            return 2

        if args.translation_language is not None and not args.clear_translation_cache:
            print("--translation-language requires --clear-translation-cache.", file=sys.stderr)
            return 2

        try:
            data_root = resolve_data_root(root, args.data_root).data_root
            if args.clear_translation_cache:
                removed = TranslationCache(data_root).clear(language=args.translation_language)
                scope = f" ({args.translation_language})" if args.translation_language else ""
                print(f"Cleared translation cache entries{scope}: {removed}")
            if args.clear_http_cache:
                print(f"Cleared HTTP cache entries: {HttpCache(data_root).clear()}")
            if args.cleanup_expired:
                print(f"Removed expired HTTP cache entries: {HttpCache(data_root).cleanup()}")
        except (OSError, ValueError) as error:
            print(f"Cache maintenance failed: {error}", file=sys.stderr)
            return 1
        return 0

    if args.command == "source-health":
        from .source_collector import SourceCollector
        from .source_health import SourceHealthStore
        from .sources import normalize_sources, source_identity

        data_root = resolve_data_root(root, args.data_root).data_root
        topic_id = IntelligenceService(root, data_root=data_root).resolve_topic_id(args.topic)
        topic_dir = data_root / "topics" / topic_id
        if not topic_dir.is_dir():
            raise FileNotFoundError(f"Topic '{topic_id}' not found")
        sources_payload = json.loads((topic_dir / "sources.json").read_text(encoding="utf-8"))
        raw_sources = sources_payload.get("sources", []) if isinstance(sources_payload, dict) else sources_payload
        source_names: dict[str, str] = {}
        for source in normalize_sources(raw_sources):
            identity = source_identity(source)
            name = str(source.get("name") or "").strip()
            if identity and name:
                source_names[identity] = name
        topic_language = "zh-CN"
        topic_config = topic_dir / "topic.json"
        if topic_config.is_file():
            topic_language = str(json.loads(topic_config.read_text(encoding="utf-8")).get("language") or "zh-CN")
        store = SourceHealthStore(topic_dir, source_names=source_names)
        if args.refresh or args.force_refresh:
            result = SourceCollector(topic_dir, force_refresh=args.force_refresh, health=store).collect()
            if result.health_notice:
                print(result.health_notice)
        print(store.report(language=topic_language))
        return 0

    if args.command == "ingest-prune":
        from .event_lifecycle import prune_ingests

        if args.keep < 0:
            print("--keep must be nonnegative.", file=sys.stderr)
            return 2
        data_root = resolve_data_root(root, args.data_root).data_root
        topic_id = IntelligenceService(root, data_root=data_root).resolve_topic_id(args.topic)
        report = prune_ingests(data_root, topic_id, keep=args.keep, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["failed"] else 0

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

    if args.command == "uninstall-skill-pack":
        installer = SkillPackInstaller(root)
        results = installer.uninstall(output_root=root, host_name=args.host, mode=args.mode)
        if not results:
            print(f"Nothing to uninstall for mode: {args.mode}")
        for result in results:
            print(f"{result.kind}: {result.mode} -> {result.target_path}")
        return 0

    if args.command == "version":
        check = check_latest_version(root)
        print(f"Skrya version: {check.local_version}")
        if check.local_revision:
            print(f"Local revision: {check.local_revision}")
        if args.check_latest and check.remote_revision:
            print(f"Remote main: {check.remote_revision}")
            if check.has_remote_update:
                print("Update available: yes")
            else:
                print("Update available: no")
        return 0

    if args.command == "upgrade":
        resolution = resolve_data_root(root, args.data_root)
        print(f"Skrya data root: {resolution.data_root}")
        if args.migrate_data:
            migrated = migrate_workspace_data(root, resolution.data_root)
            for path in migrated:
                print(f"Migrated data: {path}")
        if args.migrate_thread_naming:
            migrated = migrate_thread_naming(resolution.data_root)
            if migrated:
                for path in migrated:
                    print(f"Migrated thread naming: {path}")
            else:
                print("Migrated thread naming: no legacy files found")
        if args.check_latest:
            check = check_latest_version(root)
            print(f"Skrya version: {check.local_version}")
            if check.remote_revision:
                print(f"Remote main: {check.remote_revision}")
                print(f"Update available: {'yes' if check.has_remote_update else 'no'}")
        if args.migrate_ingest_v2:
            from .event_lifecycle import migrate_ingest_v1

            topic_id = None
            if args.topic:
                topic_id = IntelligenceService(root, data_root=resolution.data_root).resolve_topic_id(args.topic)
            migration = migrate_ingest_v1(resolution.data_root, topic_id)
            for entry in migration["migrated"]:
                print(f"Migrated ingest v2: {entry['topic_id']} (items: {entry['item_count']}, backup: {entry['backup_path']})")
            for entry in migration["already_current"]:
                print(f"Already ingest v2: {entry['topic_id']}")
            for entry in migration["failed"]:
                print(f"Ingest migration failed: {entry['topic_id']}: {entry['error']}", file=sys.stderr)
            if migration["failed"]:
                return 1
        print("Upgrade checks complete")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
