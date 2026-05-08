import json
import unittest
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

VALID_TIERS = {"llm-only", "agent-context-required", "runtime-required"}
OPENCLAW_CONTEXT_ID = "openclaw-gateway-runtime"


class AgentSkillsEvalTests(unittest.TestCase):
    def test_agent_skills_eval_config_targets_skrya_skill(self) -> None:
        config = yaml.safe_load((ROOT / "agent-skills-eval.yaml").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual("./skrya", config["root"])
        self.assertEqual([], config["include"])
        self.assertTrue(config["baseline"])
        self.assertTrue(config["strict"])
        self.assertEqual("OPENAI_API_KEY", config["apiKeyEnv"])
        self.assertEqual("agent-skills-eval --config agent-skills-eval.yaml", package["scripts"]["eval:skills"])
        self.assertEqual("node scripts/check-agent-skills-eval.mjs", package["scripts"]["eval:skills:check"])
        self.assertEqual("node scripts/runtime-openclaw-harness.mjs", package["scripts"]["eval:skills:runtime"])

    def test_eval_bank_has_all_journeys_with_at_least_five_evals_each(self) -> None:
        """The durable eval bank contains all 12 journeys with ≥5 cases each."""
        bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))

        self.assertEqual("skrya", bank["skill_name"])
        self.assertGreaterEqual(len(bank["evals"]), 60)

        counts = Counter(item["id"].split("-")[1] for item in bank["evals"])
        self.assertEqual({f"{index:02d}" for index in range(1, 13)}, set(counts))
        for index in range(1, 13):
            self.assertGreaterEqual(counts[f"{index:02d}"], 5)

        for item in bank["evals"]:
            self.assertGreaterEqual(len(item["assertions"]), 4)
            self.assertIn("journey", item["id"])
            self.assertIn("prompt", item)
            self.assertIn("expected_output", item)
            self.assertIn("tier", item)
            self.assertIn(item["tier"], VALID_TIERS)

    def test_active_evals_are_llm_only_subset_of_bank(self) -> None:
        """The active evals.json contains only llm-only cases from the eval bank."""
        bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))
        active = json.loads((ROOT / "skrya" / "evals" / "evals.json").read_text(encoding="utf-8"))

        bank_llm_ids = {item["id"] for item in bank["evals"] if item["tier"] == "llm-only"}
        active_ids = {item["id"] for item in active["evals"]}

        self.assertEqual(bank_llm_ids, active_ids,
                         "Active evals should contain exactly the llm-only cases from the eval bank")

    def test_non_llm_cases_excluded_from_active(self) -> None:
        """Cases requiring agent context or runtime are not in the active bare-LLM runner."""
        bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))
        active = json.loads((ROOT / "skrya" / "evals" / "evals.json").read_text(encoding="utf-8"))

        non_llm_ids = {item["id"] for item in bank["evals"] if item["tier"] != "llm-only"}
        active_ids = {item["id"] for item in active["evals"]}

        overlap = non_llm_ids & active_ids
        self.assertEqual(set(), overlap,
                         f"Active evals should not contain non-llm-only cases, found: {overlap}")

    def test_eval_bank_tiers_are_well_formed(self) -> None:
        """The eval bank has tier metadata and journey_tiers mapping."""
        bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))

        self.assertIn("tiers", bank)
        self.assertIn("contexts", bank)
        self.assertIn("journey_tiers", bank)
        for tier_key, tier_desc in bank["tiers"].items():
            self.assertIn(tier_key, VALID_TIERS)
            self.assertTrue(len(tier_desc) > 0)

        for journey_key, tier_val in bank["journey_tiers"].items():
            self.assertTrue(journey_key.startswith("journey-"))
            self.assertIn(tier_val, VALID_TIERS)

    def test_non_llm_cases_reference_openclaw_context(self) -> None:
        """Agent/runtime cases are tied to a concrete OpenClaw host context."""
        bank = json.loads((ROOT / "skrya" / "evals" / "eval-bank.json").read_text(encoding="utf-8"))
        context_path = ROOT / bank["contexts"][OPENCLAW_CONTEXT_ID]
        context = json.loads(context_path.read_text(encoding="utf-8"))

        self.assertEqual(OPENCLAW_CONTEXT_ID, context["id"])
        self.assertTrue(context["host"]["channel_aware"])
        self.assertEqual("<workspace>/.skrya/data", context["host"]["default_data_root"])
        self.assertTrue(context["capabilities"]["automation"]["available"])
        self.assertTrue(context["capabilities"]["messaging"]["verify_non_empty_delivery"])
        self.assertIn("delivery_bindings_path", context["topic_state"])

        for item in bank["evals"]:
            if item["tier"] == "llm-only":
                self.assertNotIn("context_ids", item)
            else:
                self.assertEqual([OPENCLAW_CONTEXT_ID], item.get("context_ids"))

    def test_runtime_harness_is_mock_openclaw_runner(self) -> None:
        """The runtime runner exists and is explicit about being a mock harness."""
        script = (ROOT / "scripts" / "runtime-openclaw-harness.mjs").read_text(encoding="utf-8")

        self.assertIn("mock-openclaw-runtime", script)
        self.assertIn("runtime-required", script)
        self.assertIn("fake tool traces", script)
        self.assertIn("create_automation", script)
        self.assertIn("render_digest", script)
        self.assertIn("uninstall_skrya", script)
        self.assertIn("runtime-report.json", script)


if __name__ == "__main__":
    unittest.main()
