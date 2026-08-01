from dataclasses import dataclass
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    storage: str = "fixture"
    database_url: str = "postgresql://rag:rag@localhost:5432/rag_demo"
    data_dir: Path = ROOT_DIR / "data"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            storage=os.getenv("DEMO_STORAGE", "fixture").lower(),
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag_demo"
            ),
        )
