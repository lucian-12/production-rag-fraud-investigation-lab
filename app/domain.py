from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class EvidenceDocument:
    id: str
    title: str
    document_type: str
    version: Optional[str]
    active: bool
    tenant_id: str
    access_roles: List[str]
    published_at: str
    content: str
    embedding: List[float]

    def public_dict(self, score: Optional[float] = None) -> Dict[str, Any]:
        value = asdict(self)
        value.pop("embedding", None)
        if score is not None:
            value["similarity"] = round(score, 4)
        return value


@dataclass(frozen=True)
class RankedEvidence:
    document: EvidenceDocument
    score: float
    excluded_reason: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        value = self.document.public_dict(self.score)
        if self.excluded_reason:
            value["excluded_reason"] = self.excluded_reason
        return value


@dataclass(frozen=True)
class RetrievalResult:
    included: List[RankedEvidence]
    discarded: List[RankedEvidence]
