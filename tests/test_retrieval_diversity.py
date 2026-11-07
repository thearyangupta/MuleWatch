from rag.search import reciprocal_rank_fusion


def test_retrieval_prefers_distinct_documents():
    vector_results = [
        {"chunk_id": 1, "source": "a", "title": "Document A"},
        {"chunk_id": 2, "source": "a", "title": "Document A"},
        {"chunk_id": 3, "source": "b", "title": "Document B"},
        {"chunk_id": 4, "source": "c", "title": "Document C"},
    ]

    results = reciprocal_rank_fusion(vector_results, [], limit=3)

    assert [result["title"] for result in results] == [
        "Document A",
        "Document B",
        "Document C",
    ]


def test_retrieval_fills_remaining_slots_with_chunks():
    vector_results = [
        {"chunk_id": 1, "source": "a", "title": "Document A"},
        {"chunk_id": 2, "source": "a", "title": "Document A"},
        {"chunk_id": 3, "source": "b", "title": "Document B"},
    ]

    results = reciprocal_rank_fusion(vector_results, [], limit=3)

    assert [result["chunk_id"] for result in results] == [1, 3, 2]


def test_retrieval_preserves_rrf_score():
    vector_results = [
        {"chunk_id": 1, "source": "a", "title": "Document A"},
    ]

    results = reciprocal_rank_fusion(vector_results, [], limit=1)

    assert len(results) == 1
    assert results[0]["rrf_score"] > 0
