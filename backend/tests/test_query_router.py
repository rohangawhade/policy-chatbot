from core.services.query_router import QueryRouter

_CHEAP = "claude-haiku-4-5-20251001"
_POWERFUL = "claude-sonnet-4-6"
_THRESHOLD = 0.4


def _router(powerful_model: str | None = _POWERFUL, threshold: float = _THRESHOLD) -> QueryRouter:
    return QueryRouter(_CHEAP, powerful_model, threshold)


def test_short_simple_query_scores_low() -> None:
    score = _router().score_complexity("What's my deductible?")

    assert score < _THRESHOLD


def test_comparison_and_multi_policy_query_scores_high() -> None:
    score = _router().score_complexity("Compare health vs dental coverage for my family")

    assert score >= _THRESHOLD


def test_comparison_keyword_contributes_to_the_score() -> None:
    without = _router().score_complexity("What does my plan include")
    with_keyword = _router().score_complexity("Compare what my plan includes")

    assert with_keyword > without


def test_mentioning_two_policy_types_scores_higher_than_mentioning_one() -> None:
    one_policy = _router().score_complexity("What is my health plan")
    two_policies = _router().score_complexity("What is my health and dental plan")

    assert two_policies > one_policy


def test_long_query_scores_higher_than_a_short_one() -> None:
    short_query = "What is covered"
    long_query = " ".join(["word"] * 25)

    short_score = _router().score_complexity(short_query)
    long_score = _router().score_complexity(long_query)

    assert long_score > short_score


def test_capitalized_words_increase_the_entity_signal() -> None:
    plain = _router().score_complexity("what plan covers this")
    with_entities = _router().score_complexity("does United Healthcare Gold cover this")

    assert with_entities > plain


def test_score_is_always_within_bounds() -> None:
    router = _router()
    queries = [
        "",
        "hi",
        "Compare Health vs Dental vs Vision Life Disability " + " ".join(["Word"] * 30),
    ]
    for query in queries:
        score = router.score_complexity(query)
        assert 0.0 <= score <= 1.0


def test_select_model_returns_cheap_below_threshold() -> None:
    router = _router()

    assert router.select_model(_THRESHOLD - 0.01) == _CHEAP


def test_select_model_returns_powerful_at_or_above_threshold() -> None:
    router = _router()

    assert router.select_model(_THRESHOLD) == _POWERFUL
    assert router.select_model(1.0) == _POWERFUL


def test_select_model_returns_cheap_when_no_powerful_model_is_configured() -> None:
    router = _router(powerful_model=None)

    assert router.select_model(1.0) == _CHEAP


def test_fallback_model_always_returns_cheap() -> None:
    router = _router()

    assert router.fallback_model() == _CHEAP
