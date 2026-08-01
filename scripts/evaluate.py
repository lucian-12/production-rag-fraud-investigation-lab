#!/usr/bin/env python3
"""Run the deterministic evaluation set without an API key or database."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.data_loader import load_case, load_documents, load_query_embeddings  # noqa: E402
from app.pipeline import InvestigationPipeline  # noqa: E402
from app.repository import FixtureEvidenceRepository  # noqa: E402


def main() -> int:
    settings = Settings()
    pipeline = InvestigationPipeline(
        FixtureEvidenceRepository(load_documents(settings.data_dir)),
        load_case(settings.data_dir),
        load_query_embeddings(settings.data_dir),
    )

    checks = [
        (
            "production rejects the superseded policy",
            lambda result: "policy-v4.8-auto-block"
            not in {item["id"] for item in result["retrieved_evidence"]},
        ),
        (
            "production rejects restricted evidence",
            lambda result: "restricted-watch-note"
            not in {item["id"] for item in result["retrieved_evidence"]},
        ),
        (
            "production recommends human verification",
            lambda result: result["brief"]["recommended_action"]
            == "Manual review + step-up authentication",
        ),
        (
            "production exposes citations",
            lambda result: len(result["brief"]["citations"]) >= 3,
        ),
    ]

    result = pipeline.investigate("risk-signals", "production")
    failures = 0
    print("Production RAG evaluation")
    print("=" * 32)
    for label, check in checks:
        passed = bool(check(result))
        failures += 0 if passed else 1
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
    print(f"\n{len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
