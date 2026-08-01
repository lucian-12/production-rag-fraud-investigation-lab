import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain import EvidenceDocument


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_case(data_dir: Path) -> Dict[str, Any]:
    return read_json(data_dir / "case.json")


def load_questions(data_dir: Path) -> List[Dict[str, Any]]:
    return read_json(data_dir / "questions.json")


def load_query_embeddings(data_dir: Path) -> Dict[str, List[float]]:
    return read_json(data_dir / "query_embeddings.json")


def load_documents(data_dir: Path) -> List[EvidenceDocument]:
    return [EvidenceDocument(**item) for item in read_json(data_dir / "documents.json")]
