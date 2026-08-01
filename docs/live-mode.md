# Extending the project to live mode

Live mode is intentionally **not implemented** in this repository. The demo works without an API
key and contains no hidden network calls.

A complete extension would add two explicit provider boundaries:

```python
class EmbeddingProvider:
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class AnswerGenerator:
    def build_brief(self, question: str, evidence: list[dict]) -> dict: ...
```

## Suggested implementation order

1. Add a provider that generates embeddings for new documents.
2. Increase the pgvector dimension to match the selected embedding model.
3. Add an ingestion endpoint with parsing, chunking and metadata validation.
4. Replace fixed questions with embedded free-text queries.
5. Add a structured-output generator for the evidence brief.
6. Validate every generated citation against the retrieved context.
7. Expand the evaluation set before enabling arbitrary documents.

The API key belongs in a local `.env` file and must never be committed. A local model provider such
as Ollama can implement the same interfaces, but it should remain optional because it adds a large
download and hardware-specific setup.
