from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import Settings
from app.data_loader import load_case, load_documents, load_query_embeddings, load_questions
from app.pipeline import InvestigationPipeline
from app.repository import FixtureEvidenceRepository, PostgresEvidenceRepository


class InvestigationRequest(BaseModel):
    question_id: str = "risk-signals"
    mode: Literal["naive", "production"] = "production"


def build_pipeline(settings: Settings) -> InvestigationPipeline:
    documents = load_documents(settings.data_dir)
    if settings.storage == "postgres":
        repository = PostgresEvidenceRepository(settings.database_url, documents)
        repository.bootstrap()
    else:
        repository = FixtureEvidenceRepository(documents)
    return InvestigationPipeline(
        repository=repository,
        case=load_case(settings.data_dir),
        query_embeddings=load_query_embeddings(settings.data_dir),
    )


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = Settings.from_env()
    application.state.settings = settings
    application.state.pipeline = build_pipeline(settings)
    application.state.case = load_case(settings.data_dir)
    application.state.questions = load_questions(settings.data_dir)
    yield


app = FastAPI(
    title="Production RAG Fraud Investigation Lab",
    version="0.1.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "storage": app.state.settings.storage,
        "api_key_required": False,
    }


@app.get("/api/scenario")
def scenario() -> dict:
    return {
        "case": app.state.case,
        "questions": app.state.questions,
        "modes": [
            {
                "id": "naive",
                "label": "Naive RAG",
                "description": "Vector similarity only; no evidence validation.",
            },
            {
                "id": "production",
                "label": "Production RAG",
                "description": "Version, tenant and permission filters with visible citations.",
            },
        ],
    }


@app.post("/api/investigate")
def investigate(request: InvestigationRequest) -> dict:
    try:
        return app.state.pipeline.investigate(request.question_id, request.mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/compare/{question_id}")
def compare(question_id: str) -> dict:
    try:
        return app.state.pipeline.compare(question_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
