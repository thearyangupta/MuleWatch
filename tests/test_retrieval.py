from rag.search import hybrid_search, load_embedding_model

RETRIEVAL_CASES = [
    (
        "rapid pass-through of funds through an account",
        "Proceeds of fraud - Detecting and preventing money mules",
    ),
    (
        "money mule account detection systems and controls",
        "Proceeds of fraud - Detecting and preventing money mules",
    ),
    (
        "using fraud databases to identify mule accounts",
        "Firms' use of the National Fraud Database (NFD) "
        "and money mule account detection tools",
    ),
    (
        "how criminals cash out money from mule accounts",
        "Money mules: mule activity and cashing out findings",
    ),
    (
        "warning signs of money transfer scams",
        "Money transfer scams",
    ),
    (
        "criminals recruit people to move illegal money",
        "Don't become a money mule: what you need to know",
    ),
    (
        "risks and consequences of acting as a money mule",
        "Money mules - what are the risks?",
    ),
    (
        "criminal networks recruiting money mules online",
        "#YourAccountYourCrime: Global campaign exposes use of money mules",
    ),
    (
        "financial exploitation and recruitment of money mules",
        "Money mule and financial exploitation action plan",
    ),
    (
        "pass-through ratio and dwell time account features",
        "MuleWatch Feature Definitions",
    ),
]


def test_retrieval_hit_rate_at_5():
    model = load_embedding_model()

    hits = 0

    for query, expected_title in RETRIEVAL_CASES:
        results = hybrid_search(
            query,
            limit=5,
            model=model,
        )

        returned_titles = {result["title"] for result in results}

        if expected_title in returned_titles:
            hits += 1

    hit_rate = hits / len(RETRIEVAL_CASES)

    print(f"\nRetrieval hit rate@5: {hits}/{len(RETRIEVAL_CASES)} = {hit_rate:.0%}")

    assert len(RETRIEVAL_CASES) == 10
    assert hit_rate >= 0.8
