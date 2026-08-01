from typing import Any, Dict, List, Optional

from app.domain import RankedEvidence
from app.repository import EvidenceRepository


QUESTION_COPY = {
    "risk-signals": "Which signals increase or reduce the risk?",
    "current-policy": "What does the current fraud policy require?",
    "device-history": "Has this customer used the device or network before?",
    "similar-cases": "What happened in similar investigations?",
}


class InvestigationPipeline:
    def __init__(
        self,
        repository: EvidenceRepository,
        case: Dict[str, Any],
        query_embeddings: Dict[str, List[float]],
    ) -> None:
        self.repository = repository
        self.case = case
        self.query_embeddings = query_embeddings

    def investigate(self, question_id: str, mode: str) -> Dict[str, Any]:
        if question_id not in self.query_embeddings:
            raise ValueError(f"Unknown question: {question_id}")
        if mode not in ("naive", "production"):
            raise ValueError("Mode must be 'naive' or 'production'")

        retrieval = self.repository.retrieve(
            self.query_embeddings[question_id],
            mode=mode,
            tenant_id=self.case["tenant_id"],
            role=self.case["analyst_role"],
        )
        brief = self._build_brief(question_id, mode, retrieval.included)
        return {
            "case_id": self.case["case_id"],
            "mode": mode,
            "question_id": question_id,
            "question": QUESTION_COPY[question_id],
            "retrieved_evidence": [item.public_dict() for item in retrieval.included],
            "discarded_evidence": [item.public_dict() for item in retrieval.discarded],
            "pipeline": self._pipeline_trace(mode, retrieval.included, retrieval.discarded),
            "brief": brief,
        }

    def compare(self, question_id: str) -> Dict[str, Any]:
        return {
            "question_id": question_id,
            "naive": self.investigate(question_id, "naive"),
            "production": self.investigate(question_id, "production"),
        }

    @staticmethod
    def _pipeline_trace(
        mode: str, included: List[RankedEvidence], discarded: List[RankedEvidence]
    ) -> List[Dict[str, Any]]:
        if mode == "naive":
            return [
                {"stage": "retrieve", "status": "complete", "detail": "Vector top-k only"},
                {
                    "stage": "filter",
                    "status": "skipped",
                    "detail": "No version, tenant or permission checks",
                },
                {
                    "stage": "generate",
                    "status": "warning",
                    "detail": f"Generated from {len(included)} unverified sources",
                },
            ]
        return [
            {
                "stage": "exact facts",
                "status": "complete",
                "detail": "Transaction and customer facts read from relational data",
            },
            {
                "stage": "retrieve",
                "status": "complete",
                "detail": f"{len(included)} permitted sources selected",
            },
            {
                "stage": "filter",
                "status": "complete",
                "detail": f"{len(discarded)} stale or restricted sources rejected",
            },
            {
                "stage": "cite",
                "status": "complete",
                "detail": "Every claim maps to visible evidence",
            },
        ]

    def _build_brief(
        self, question_id: str, mode: str, evidence: List[RankedEvidence]
    ) -> Dict[str, Any]:
        citations = [
            {"id": index + 1, "document_id": item.document.id, "title": item.document.title}
            for index, item in enumerate(evidence)
        ]
        citation_by_document = {
            item["document_id"]: item["id"] for item in citations
        }

        def cite(document_id: str) -> str:
            citation = citation_by_document.get(document_id)
            return f"[{citation}]" if citation else ""

        def cited_statement(text: str, document_id: str) -> Optional[str]:
            citation = cite(document_id)
            return f"{text} {citation}" if citation else None

        def compact(*statements: Optional[str]) -> List[str]:
            return [statement for statement in statements if statement]

        if mode == "naive":
            if question_id == "current-policy":
                summary = (
                    "The retrieved policies conflict. Similarity-only RAG surfaces both the current "
                    "step-up rule and a superseded automatic-block rule without resolving version status."
                )
                primary_label = "Retrieved policy claims"
                secondary_label = "Unresolved conflict"
                missing_label = "Validation skipped"
                primary_signals = compact(
                    cited_statement(
                        "Policy v6.2 requires step-up authentication and manual review",
                        "policy-v6.2-step-up",
                    ),
                    cited_statement(
                        "Policy v4.8 recommends an automatic block",
                        "policy-v4.8-auto-block",
                    ),
                )
                secondary_signals = compact(
                    cited_statement(
                        "A restricted merchant note also influences the context",
                        "restricted-watch-note",
                    )
                )
                missing_evidence = [
                    "No active-version check was performed.",
                    "No permission check was performed.",
                ]
                recommended_action = "Block based on unresolved policy context"
                confidence = "High, but unreliable"
            elif question_id == "device-history":
                summary = (
                    "The new device and Singapore hosting network look suspicious, and similarity-only "
                    "retrieval overweights account-takeover examples."
                )
                primary_label = "Device signals"
                secondary_label = "Cases used as proof"
                missing_label = "Context ignored"
                primary_signals = compact(
                    cited_statement("The device is new for Elena", "device-fr2048"),
                    cited_statement(
                        "The request comes from a Singapore hosting network",
                        "device-fr2048",
                    ),
                )
                secondary_signals = compact(
                    cited_statement(
                        "A similar account was confirmed as takeover",
                        "case-ato-118",
                    ),
                    cited_statement(
                        "A cross-tenant case is treated as usable evidence",
                        "other-tenant-case",
                    ),
                )
                missing_evidence = [
                    "Trusted-address history is not weighed against the device signal.",
                    "Tenant boundaries are not checked.",
                ]
                recommended_action = "Block as likely account takeover"
                confidence = "High, but unreliable"
            elif question_id == "similar-cases":
                summary = (
                    "The nearest precedents disagree: one was legitimate travel and others were "
                    "account takeover. Naive RAG still treats similarity as a verdict."
                )
                primary_label = "Account takeover precedents"
                secondary_label = "Contradicting precedent"
                missing_label = "Boundaries ignored"
                primary_signals = compact(
                    cited_statement("A similar case was account takeover", "case-ato-118"),
                    cited_statement(
                        "Another takeover case belongs to a different tenant",
                        "other-tenant-case",
                    ),
                )
                secondary_signals = compact(
                    cited_statement(
                        "The most similar case was a legitimate travel purchase",
                        "case-legit-travel-041",
                    )
                )
                missing_evidence = [
                    "No tenant validation was performed.",
                    "No rule explains how conflicting precedents should be weighed.",
                ]
                recommended_action = "Escalate as likely account takeover"
                confidence = "Medium, but unreliable"
            else:
                summary = (
                    "Block the transaction. A high-value purchase from a new foreign device "
                    "matches an automatic-block policy and a merchant watch note."
                )
                primary_label = "Risk signals"
                secondary_label = "Trust signals"
                missing_label = "Validation skipped"
                primary_signals = compact(
                    cited_statement(
                        "Amount is far above the customer's normal range",
                        "case-ato-118",
                    ),
                    cited_statement(
                        "The transaction used a new Singapore device",
                        "device-fr2048",
                    ),
                    cited_statement(
                        "The merchant appears on an internal watch note",
                        "restricted-watch-note",
                    ),
                )
                secondary_signals = []
                missing_evidence = ["No source validity or permission checks were performed."]
                recommended_action = "Block"
                confidence = "High, but unreliable"

            return {
                "summary": summary,
                "primary_label": primary_label,
                "secondary_label": secondary_label,
                "missing_label": missing_label,
                "risk_signals": primary_signals,
                "trust_signals": secondary_signals,
                "missing_evidence": missing_evidence,
                "recommended_action": recommended_action,
                "confidence": confidence,
                "warning": "This answer may cite stale or restricted evidence.",
                "citations": citations,
            }

        if question_id == "current-policy":
            summary = (
                "Fraud Policy v6.2 requires step-up authentication and manual review; it does "
                "not permit an automatic block from these signals alone."
            )
            primary_label = "Policy requirements"
            secondary_label = "Case facts that trigger review"
            missing_label = "Policy cannot determine"
            primary_signals = compact(
                cited_statement(
                    "Require step-up authentication for this high-value new-device purchase",
                    "policy-v6.2-step-up",
                ),
                cited_statement(
                    "Route foreign or hosted network traffic to manual review",
                    "policy-v6.2-step-up",
                ),
                cited_statement(
                    "Do not automatically block without additional evidence",
                    "policy-v6.2-step-up",
                ),
            )
            secondary_signals = compact(
                cited_statement(
                    "$4,850 is more than 16× Elena's typical purchase",
                    "customer-profile-elena",
                ),
                cited_statement(
                    "The device and Singapore hosting network are new",
                    "device-fr2048",
                ),
            )
            missing_evidence = [
                "Policy defines the review process, not the final fraud verdict.",
                "The step-up authentication result is not yet known.",
            ]
            recommended_action = "Require step-up authentication, then manual review"
            confidence = "High on policy, not on verdict"
        elif question_id == "device-history":
            summary = (
                "The device and Singapore hosting network are new for Elena. The trusted Berlin "
                "delivery address is consistent with prior successful purchases."
            )
            primary_label = "New device evidence"
            secondary_label = "Established account context"
            missing_label = "What to verify next"
            primary_signals = compact(
                cited_statement(
                    "Device fingerprint 9F:22 has never appeared on Elena's account",
                    "device-fr2048",
                ),
                cited_statement(
                    "The request originated from a Singapore hosting ASN",
                    "device-fr2048",
                ),
                cited_statement(
                    "No trusted-session cookie was presented",
                    "device-fr2048",
                ),
            )
            secondary_signals = compact(
                cited_statement(
                    "Elena's account has four years of history",
                    "customer-profile-elena",
                ),
                cited_statement(
                    "The Berlin address has 17 successful purchases",
                    "customer-profile-elena",
                ),
            )
            missing_evidence = [
                "Whether Elena currently controls this device.",
                "Whether the customer can complete step-up authentication.",
            ]
            recommended_action = "Challenge the session with step-up authentication"
            confidence = "High on device novelty"
        elif question_id == "similar-cases":
            summary = (
                "Historical cases show both account takeover and legitimate travel purchases. "
                "The evidence supports verification, not a final fraud verdict."
            )
            primary_label = "Account takeover precedent"
            secondary_label = "Legitimate precedent"
            missing_label = "Why precedent is not a verdict"
            primary_signals = compact(
                cited_statement(
                    "A four-year account placed a $5,200 camera order from a new Singapore device; step-up failed",
                    "case-ato-118",
                )
            )
            secondary_signals = compact(
                cited_statement(
                    "A $4,600 photography purchase from Asia was legitimate after step-up succeeded",
                    "case-legit-travel-041",
                )
            )
            missing_evidence = [
                "The precedents have opposite outcomes and cannot classify Elena's case alone.",
                "The step-up result would distinguish the two patterns.",
            ]
            recommended_action = "Use precedents to guide verification, not automate the verdict"
            confidence = "Medium"
        else:
            summary = (
                "Three signals raise risk, while account history, merchant verification and the "
                "delivery address reduce certainty."
            )
            primary_label = "Risk signals"
            secondary_label = "Trust signals"
            missing_label = "Still unknown"
            primary_signals = compact(
                cited_statement(
                    "$4,850 is more than 16× Elena's typical purchase",
                    "customer-profile-elena",
                ),
                cited_statement(
                    "The device has never been used on this account",
                    "device-fr2048",
                ),
                cited_statement(
                    "The IP belongs to a Singapore hosting network",
                    "device-fr2048",
                ),
            )
            secondary_signals = compact(
                cited_statement(
                    "The customer account is four years old",
                    "customer-profile-elena",
                ),
                cited_statement(
                    "Northlight Cameras is a verified merchant",
                    "merchant-northlight",
                ),
                cited_statement(
                    "The Berlin delivery address was previously used successfully",
                    "customer-profile-elena",
                ),
            )
            missing_evidence = [
                "Whether Elena is currently travelling.",
                "Whether the customer can complete step-up authentication.",
            ]
            recommended_action = "Manual review + step-up authentication"
            confidence = "Medium"

        return {
            "summary": summary,
            "primary_label": primary_label,
            "secondary_label": secondary_label,
            "missing_label": missing_label,
            "risk_signals": primary_signals,
            "trust_signals": secondary_signals,
            "missing_evidence": missing_evidence,
            "recommended_action": recommended_action,
            "confidence": confidence,
            "warning": None,
            "citations": citations,
        }
