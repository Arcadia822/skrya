import unittest
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESETS_DIR = REPO_ROOT / "source-curation" / "presets"

REQUIRED_DOMAINS = [
    "ai-llm",
    "new-energy-vehicles",
    "developer-tools",
    "cryptocurrency",
    "technology-news",
]

ALLOWED_SOURCE_TYPES = {"rss", "rsshub", "runtime-retrieval"}
ALLOWED_CAPABILITIES = {
    "web_search",
    "news_search",
    "social_search",
    "site_search",
    "document_fetch",
}
FORBIDDEN_URL_PATTERNS = {"example.com", "placeholder", "fake", "foo.bar"}


def load_all_presets() -> dict[str, dict]:
    presets = {}
    for path in sorted(PRESETS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        presets[path.stem] = data
    return presets


class SourcePresetsContractTests(unittest.TestCase):
    def test_all_five_required_domains_exist_as_yaml(self) -> None:
        self.assertTrue(PRESETS_DIR.is_dir(), f"Presets directory should exist: {PRESETS_DIR}")
        existing_stems = {p.stem for p in PRESETS_DIR.glob("*.yaml")}
        missing = set(REQUIRED_DOMAINS) - existing_stems
        self.assertFalse(missing, f"Missing required domain presets: {missing}")

    def test_presets_conform_to_structural_schema(self) -> None:
        presets = load_all_presets()
        for preset_id in REQUIRED_DOMAINS:
            self.assertIn(preset_id, presets, f"Preset {preset_id} must be loadable")
            preset = presets[preset_id]
            self.assertEqual(preset.get("preset_id"), preset_id)
            self.assertTrue(isinstance(preset.get("name"), str) and preset["name"].strip())
            self.assertTrue(isinstance(preset.get("description"), str) and preset["description"].strip())

            tags = preset.get("tags")
            self.assertTrue(isinstance(tags, list) and len(tags) > 0)
            self.assertEqual(len(tags), len(set(tags)), f"Duplicate tags found in {preset_id}")

            source_groups = preset.get("source_groups")
            self.assertTrue(isinstance(source_groups, list) and len(source_groups) > 0)

            seen_source_identities: set[tuple[str, str]] = set()

            for group in source_groups:
                self.assertTrue(isinstance(group.get("name"), str) and group["name"].strip())
                sources = group.get("sources", [])
                self.assertTrue(isinstance(sources, list) and len(sources) > 0)

                for source in sources:
                    name = source.get("name")
                    stype = source.get("type")
                    self.assertTrue(isinstance(name, str) and name.strip())
                    self.assertIn(stype, ALLOWED_SOURCE_TYPES)

                    if stype == "rss":
                        url = source.get("url")
                        self.assertTrue(isinstance(url, str) and (url.startswith("https://") or url.startswith("http://")))
                        self.assertFalse(any(bad in url.lower() for bad in FORBIDDEN_URL_PATTERNS))
                        source_key = (stype, url.strip())
                    elif stype == "rsshub":
                        route = source.get("route")
                        self.assertTrue(isinstance(route, str) and route.startswith("/"))
                        if "instance_urls" in source:
                            self.assertTrue(isinstance(source["instance_urls"], list))
                            for inst in source["instance_urls"]:
                                self.assertTrue(inst.startswith("https://"))
                        source_key = (stype, route.strip())
                    elif stype == "runtime-retrieval":
                        capabilities = source.get("capabilities", [])
                        self.assertTrue(isinstance(capabilities, list) and len(capabilities) > 0)
                        for cap in capabilities:
                            self.assertIn(cap, ALLOWED_CAPABILITIES)
                        queries = source.get("queries", [])
                        self.assertTrue(isinstance(queries, list) and len(queries) > 0)
                        source_key = (stype, name.strip())
                    else:
                        source_key = (stype, name.strip())

                    self.assertNotIn(
                        source_key,
                        seen_source_identities,
                        f"Duplicate source identity {source_key} in preset {preset_id}",
                    )
                    seen_source_identities.add(source_key)


if __name__ == "__main__":
    unittest.main()
