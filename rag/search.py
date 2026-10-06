import os
from collections import defaultdict

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

DATABASE_URL = os.getenv(
    "MULEWATCH_DATABASE_URL",
    "postgresql://mulewatch:mulewatch_dev@localhost:5432/mulewatch",
)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

SEARCH_LIMIT = 20
RRF_K = 60


def load_embedding_model() -> SentenceTransformer:
    """Load the same embedding model used during ingestion."""

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def vector_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = SEARCH_LIMIT,
) -> list[dict]:
    """Return chunks ranked by cosine similarity."""

    rows = conn.execute(
        """
        SELECT
            chunk_id,
            content,
            source,
            title,
            section,
            url,
            source_date,
            embedding <=> %s::vector AS distance
        FROM typology_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (
            query_embedding,
            query_embedding,
            limit,
        ),
    ).fetchall()

    return [
        {
            "chunk_id": row[0],
            "content": row[1],
            "source": row[2],
            "title": row[3],
            "section": row[4],
            "url": row[5],
            "source_date": row[6],
            "vector_distance": float(row[7]),
        }
        for row in rows
    ]


def full_text_search(
    conn: psycopg.Connection,
    query: str,
    limit: int = SEARCH_LIMIT,
) -> list[dict]:
    """Return chunks ranked by PostgreSQL full-text search."""

    rows = conn.execute(
        """
        SELECT
            chunk_id,
            content,
            source,
            title,
            section,
            url,
            source_date,
            ts_rank(
                to_tsvector('english', content),
                plainto_tsquery('english', %s)
            ) AS text_rank
        FROM typology_chunks
        WHERE to_tsvector('english', content)
              @@ plainto_tsquery('english', %s)
        ORDER BY text_rank DESC
        LIMIT %s
        """,
        (
            query,
            query,
            limit,
        ),
    ).fetchall()

    return [
        {
            "chunk_id": row[0],
            "content": row[1],
            "source": row[2],
            "title": row[3],
            "section": row[4],
            "url": row[5],
            "source_date": row[6],
            "text_rank": float(row[7]),
        }
        for row in rows
    ]


def reciprocal_rank_fusion(
    vector_results: list[dict],
    text_results: list[dict],
    limit: int = 5,
) -> list[dict]:
    """Merge vector and full-text rankings using reciprocal rank fusion."""

    scores = defaultdict(float)
    results_by_id = {}

    for rank, result in enumerate(vector_results, start=1):
        chunk_id = result["chunk_id"]

        scores[chunk_id] += 1 / (RRF_K + rank)
        results_by_id[chunk_id] = result.copy()

    for rank, result in enumerate(text_results, start=1):
        chunk_id = result["chunk_id"]

        scores[chunk_id] += 1 / (RRF_K + rank)

        if chunk_id not in results_by_id:
            results_by_id[chunk_id] = result.copy()
        else:
            results_by_id[chunk_id].update(result)

    ranked_ids = sorted(
        scores,
        key=scores.get,
        reverse=True,
    )

    results = []

    for chunk_id in ranked_ids[:limit]:
        result = results_by_id[chunk_id]
        result["rrf_score"] = scores[chunk_id]
        results.append(result)

    return results


def hybrid_search(
    query: str,
    limit: int = 5,
    *,
    model: SentenceTransformer | None = None,
) -> list[dict]:
    """Search the typology knowledge base using vector + FTS + RRF."""

    if model is None:
        model = load_embedding_model()

    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    candidate_limit = max(SEARCH_LIMIT, limit)

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)

        vector_results = vector_search(
            conn,
            query_embedding,
            candidate_limit,
        )

        text_results = full_text_search(
            conn,
            query,
            candidate_limit,
        )

    return reciprocal_rank_fusion(
        vector_results,
        text_results,
        limit,
    )


if __name__ == "__main__":
    query = "rapid pass-through of funds"

    results = hybrid_search(query)

    print(f"Query: {query}\n")

    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. {result['chunk_id']} "
            f"[{result['source']} | {result['section']}] "
            f"RRF={result['rrf_score']:.6f}"
        )
