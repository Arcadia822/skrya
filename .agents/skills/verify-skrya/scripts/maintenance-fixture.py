"""Loopback-only CLI recipe inputs and read-only data-root manifests."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.sax.saxutils import escape


def manifest(root):
    entries = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(base) / name
            key = str(path.relative_to(root))
            if path.is_symlink():
                entries[key] = {"link": os.readlink(path)}
            elif path.is_dir():
                entries[key] = {"directory": True}
            else:
                entries[key] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(entries, ensure_ascii=False, sort_keys=True, indent=2))


def serve(scratch):
    marker = scratch / ".verify-skrya-owner"
    if not marker.is_file() or scratch.name != "verify-skrya-" + marker.read_text():
        raise SystemExit("Refusing fixture writes outside an owned verification run")
    work = scratch / "work"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with (work / "requests.jsonl").open("a") as log:
                log.write(json.dumps({"path": self.path, "headers": dict(self.headers)}) + "\n")
            if self.path == "/broken" or (work / "fail-feed").exists():
                self.send_error(503, "isolated fixture failure")
                return
            title = (work / "feed-title.txt").read_text().strip()
            body = ("<rss version='2.0'><channel><title>验证信源</title><item><title>"
                    + escape(title) + "</title><link>https://example.invalid/live-1</link>"
                    "<description>验证摘要：同一事件的本地信源更新。</description>"
                    "</item></channel></rss>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("ETag", '"fixture-v1"')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    now = datetime.now(timezone.utc).isoformat()
    (work / "feed-title.txt").write_text("验证用条目：本地信源发布推理评测基准")
    sources = {"sources": [
        {"id": "fixture-feed", "name": "验证信源", "type": "rsshub", "enabled": True,
         "route": "/feed", "instance_urls": [url], "timeout_ms": 1000},
        {"id": "fixture-broken", "name": "验证失败信源", "type": "rsshub", "enabled": True,
         "route": "/broken", "instance_urls": [url], "timeout_ms": 1000,
         "fallback": {"capabilities": ["web_search"], "queries": ["验证失败信源 推理评测"]}},
        {"id": "fixture-runtime", "name": "验证检索", "type": "runtime-retrieval", "enabled": True,
         "capabilities": ["web_search"], "queries": ["推理评测"]},
    ]}
    source_text = json.dumps(sources, ensure_ascii=False)
    (work / "sources-original.json").write_text(source_text)
    (scratch / "data/topics/agi-news/sources.json").write_text(source_text)
    payload = {"interface_version": "skrya.ingest.v2", "topic_id": "agi-news", "retrieved_at": now,
               "producer": {"name": "verify-fixture", "kind": "runtime-skill", "persistent": False},
               "items": [{"id": "fixture-ingest", "source_id": "fixture-runtime",
                          "title": "验证用条目：检索信源发布新的推理基准", "source_name": "验证检索",
                          "url": "https://example.invalid/ingest-1", "fetched_at": now,
                          "language": "zh-CN", "summary": "验证摘要：新的推理基准公布。"}]}
    (work / "ingest.json").write_text(json.dumps(payload, ensure_ascii=False))
    (work / "fixture-ready.json").write_text(json.dumps({"url": url, "retrieved_at": now}))
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve", "manifest"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "manifest":
        manifest(args.path)
    else:
        serve(args.path)
