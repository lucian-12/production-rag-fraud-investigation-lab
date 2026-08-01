from abc import ABC, abstractmethod
import math
from typing import Iterable, List, Sequence, Tuple

from app.domain import EvidenceDocument, RankedEvidence, RetrievalResult


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def exclusion_reason(document: EvidenceDocument, tenant_id: str, role: str) -> str:
    if not document.active:
        return "superseded version"
    if document.tenant_id not in ("global", tenant_id):
        return "different tenant"
    if role not in document.access_roles:
        return "insufficient permissions"
    return ""


def rank_documents(
    documents: Iterable[EvidenceDocument], query_embedding: Sequence[float]
) -> List[RankedEvidence]:
    ranked = [
        RankedEvidence(document=document, score=cosine_similarity(document.embedding, query_embedding))
        for document in documents
    ]
    return sorted(ranked, key=lambda item: item.score, reverse=True)


class EvidenceRepository(ABC):
    @abstractmethod
    def retrieve(
        self,
        query_embedding: Sequence[float],
        mode: str,
        tenant_id: str,
        role: str,
        limit: int = 5,
    ) -> RetrievalResult:
        raise NotImplementedError


class FixtureEvidenceRepository(EvidenceRepository):
    def __init__(self, documents: Iterable[EvidenceDocument]):
        self.documents = list(documents)

    def retrieve(
        self,
        query_embedding: Sequence[float],
        mode: str,
        tenant_id: str,
        role: str,
        limit: int = 5,
    ) -> RetrievalResult:
        ranked = rank_documents(self.documents, query_embedding)
        if mode == "naive":
            return RetrievalResult(included=ranked[:limit], discarded=[])

        included: List[RankedEvidence] = []
        discarded: List[RankedEvidence] = []
        for item in ranked:
            reason = exclusion_reason(item.document, tenant_id, role)
            if reason:
                discarded.append(
                    RankedEvidence(
                        document=item.document,
                        score=item.score,
                        excluded_reason=reason,
                    )
                )
            elif len(included) < limit:
                included.append(item)
        return RetrievalResult(included=included, discarded=discarded)


class PostgresEvidenceRepository(EvidenceRepository):
    """pgvector-backed retrieval used by Docker Compose.

    The database calculates similarity. Production filtering is applied in SQL so stale,
    cross-tenant and restricted documents never enter the generation context.
    """

    def __init__(self, database_url: str, documents: Iterable[EvidenceDocument]):
        self.database_url = database_url
        self.seed_documents = list(documents)

    @staticmethod
    def _vector_literal(values: Sequence[float]) -> str:
        return "[" + ",".join(str(value) for value in values) + "]"

    def bootstrap(self) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS evidence_documents (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        version TEXT,
                        active BOOLEAN NOT NULL,
                        tenant_id TEXT NOT NULL,
                        access_roles JSONB NOT NULL,
                        published_at DATE NOT NULL,
                        content TEXT NOT NULL,
                        embedding VECTOR(6) NOT NULL
                    )
                    """
                )
                for document in self.seed_documents:
                    cursor.execute(
                        """
                        INSERT INTO evidence_documents (
                            id, title, document_type, version, active, tenant_id,
                            access_roles, published_at, content, embedding
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::vector)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            document_type = EXCLUDED.document_type,
                            version = EXCLUDED.version,
                            active = EXCLUDED.active,
                            tenant_id = EXCLUDED.tenant_id,
                            access_roles = EXCLUDED.access_roles,
                            published_at = EXCLUDED.published_at,
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            document.id,
                            document.title,
                            document.document_type,
                            document.version,
                            document.active,
                            document.tenant_id,
                            __import__("json").dumps(document.access_roles),
                            document.published_at,
                            document.content,
                            self._vector_literal(document.embedding),
                        ),
                    )
            connection.commit()

    @staticmethod
    def _to_document(row: Tuple) -> EvidenceDocument:
        return EvidenceDocument(
            id=row[0],
            title=row[1],
            document_type=row[2],
            version=row[3],
            active=row[4],
            tenant_id=row[5],
            access_roles=row[6],
            published_at=str(row[7]),
            content=row[8],
            embedding=[],
        )

    def _query(self, query_embedding: Sequence[float], where: str, params: Tuple) -> List[RankedEvidence]:
        import psycopg

        vector = self._vector_literal(query_embedding)
        sql = f"""
            SELECT id, title, document_type, version, active, tenant_id,
                   access_roles, published_at, content,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM evidence_documents
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT 12
        """
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (vector, *params, vector))
                return [
                    RankedEvidence(document=self._to_document(row[:9]), score=float(row[9]))
                    for row in cursor.fetchall()
                ]

    def retrieve(
        self,
        query_embedding: Sequence[float],
        mode: str,
        tenant_id: str,
        role: str,
        limit: int = 5,
    ) -> RetrievalResult:
        all_ranked = self._query(query_embedding, "", ())
        if mode == "naive":
            return RetrievalResult(included=all_ranked[:limit], discarded=[])

        valid = self._query(
            query_embedding,
            """WHERE active IS TRUE
               AND tenant_id IN ('global', %s)
               AND access_roles ? %s""",
            (tenant_id, role),
        )[:limit]
        valid_ids = {item.document.id for item in valid}
        discarded = []
        for item in all_ranked:
            if item.document.id in valid_ids:
                continue
            reason = exclusion_reason(item.document, tenant_id, role)
            if reason:
                discarded.append(
                    RankedEvidence(item.document, item.score, excluded_reason=reason)
                )
        return RetrievalResult(included=valid, discarded=discarded)
