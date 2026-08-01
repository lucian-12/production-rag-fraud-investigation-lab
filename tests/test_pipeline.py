import unittest

from app.config import Settings
from app.data_loader import load_case, load_documents, load_query_embeddings
from app.pipeline import InvestigationPipeline
from app.repository import FixtureEvidenceRepository, cosine_similarity


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        settings = Settings()
        cls.pipeline = InvestigationPipeline(
            repository=FixtureEvidenceRepository(load_documents(settings.data_dir)),
            case=load_case(settings.data_dir),
            query_embeddings=load_query_embeddings(settings.data_dir),
        )

    def test_cosine_similarity(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)

    def test_naive_mode_uses_unverified_evidence(self) -> None:
        result = self.pipeline.investigate("risk-signals", "naive")
        ids = {item["id"] for item in result["retrieved_evidence"]}
        self.assertIn("restricted-watch-note", ids)
        self.assertEqual(result["brief"]["recommended_action"], "Block")
        self.assertIsNotNone(result["brief"]["warning"])

    def test_production_mode_rejects_invalid_evidence(self) -> None:
        result = self.pipeline.investigate("risk-signals", "production")
        included_ids = {item["id"] for item in result["retrieved_evidence"]}
        discarded = {item["id"]: item["excluded_reason"] for item in result["discarded_evidence"]}

        self.assertNotIn("restricted-watch-note", included_ids)
        self.assertNotIn("policy-v4.8-auto-block", included_ids)
        self.assertNotIn("other-tenant-case", included_ids)
        self.assertEqual(discarded["restricted-watch-note"], "insufficient permissions")
        self.assertEqual(discarded["policy-v4.8-auto-block"], "superseded version")
        self.assertEqual(discarded["other-tenant-case"], "different tenant")
        self.assertEqual(
            result["brief"]["recommended_action"],
            "Manual review + step-up authentication",
        )

    def test_current_policy_prefers_active_version(self) -> None:
        result = self.pipeline.investigate("current-policy", "production")
        included_ids = {item["id"] for item in result["retrieved_evidence"]}
        self.assertIn("policy-v6.2-step-up", included_ids)
        self.assertNotIn("policy-v4.8-auto-block", included_ids)
        self.assertIn("v6.2", result["brief"]["summary"])

    def test_compare_returns_both_modes(self) -> None:
        result = self.pipeline.compare("similar-cases")
        self.assertEqual(result["naive"]["mode"], "naive")
        self.assertEqual(result["production"]["mode"], "production")

    def test_every_production_signal_has_a_visible_citation(self) -> None:
        for question_id in self.pipeline.query_embeddings:
            result = self.pipeline.investigate(question_id, "production")
            for field in ("risk_signals", "trust_signals"):
                for signal in result["brief"][field]:
                    self.assertRegex(signal, r"\[\d+\]$")

    def test_each_question_builds_a_distinct_brief(self) -> None:
        briefs = {
            question_id: self.pipeline.investigate(question_id, "production")["brief"]
            for question_id in self.pipeline.query_embeddings
        }

        self.assertEqual(len({brief["primary_label"] for brief in briefs.values()}), 4)
        self.assertEqual(len({brief["recommended_action"] for brief in briefs.values()}), 4)
        self.assertEqual(len({brief["summary"] for brief in briefs.values()}), 4)

    def test_unknown_question_fails_cleanly(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown question"):
            self.pipeline.investigate("unknown", "production")


if __name__ == "__main__":
    unittest.main()
