"""Scores query complexity and routes to a model tier, with automatic
fallback (files/plan.md Step 6.2). `select_model`/`fallback_model`
follow `files/coding-standards.md` section 17's Multi-Model Fallback
Pattern logic — but that section's own snippet takes a whole
`LLMConfig` object, which would violate section 3's own import boundary
("core/services/ imports from core/ports/ and core/domain/ ONLY" —
`config.py` is neither). Every other Phase 3/4/6 service instead takes
plain scalar values as constructor params (caller decides, service has
no opinion) — `cheap_model`/`powerful_model`/`complexity_threshold`
here, matching that established pattern over section 17's literal
signature.

Routing decisions aren't logged by this class itself — the complexity
score and selected model tier are meant to land on `LLMCostLog`
(`core/domain/analytics.py` already has `query_complexity_score`/
`model_tier` fields for exactly this), which Step 6.5's streaming
generation writes once a call actually happens. `QueryRouter` stays a
pure, stateless scoring/selection utility with no event bus or
repository dependency.
"""

_COMPARISON_KEYWORDS = frozenset(
    {
        "compare",
        "comparison",
        "versus",
        " vs ",
        "vs.",
        "difference",
        "better",
        "which is",
        "explain why",
        "recommend",
        "pros and cons",
    }
)
_POLICY_TYPE_KEYWORDS = frozenset({"health", "dental", "vision", "life", "disability"})
_LONG_QUERY_WORD_THRESHOLD = 20
_MULTI_POLICY_SIGNAL_THRESHOLD = 2
_ENTITY_SIGNAL_THRESHOLD = 3


class QueryRouter:
    """Routes queries to the appropriate model tier with automatic fallback.

    Attributes:
        cheap_model: Always the fallback tier.
        powerful_model: `None` means every query routes to `cheap_model`
            regardless of complexity — plan.md's "if `powerful_model` is
            empty or its key is missing, every query falls back to
            `cheap_model` — no code changes needed."
        complexity_threshold: `select_model` routes to `powerful_model`
            only at or above this score.
    """

    def __init__(
        self, cheap_model: str, powerful_model: str | None, complexity_threshold: float
    ) -> None:
        self._cheap_model = cheap_model
        self._powerful_model = powerful_model
        self._complexity_threshold = complexity_threshold

    def score_complexity(self, query_text: str) -> float:
        """Score `query_text`'s complexity on a 0.0-1.0 scale.

        The average of four signals, each independently normalized to
        [0.0, 1.0] (files/plan.md's named signals): a comparison/
        reasoning keyword, how many distinct policy types are
        mentioned, query length, and a rough entity-count proxy
        (capitalized words after the first).
        """
        lowered = query_text.lower()
        signals = (
            1.0 if self._has_comparison_keyword(lowered) else 0.0,
            self._multi_policy_signal(lowered),
            self._length_signal(query_text),
            self._entity_count_signal(query_text),
        )
        return sum(signals) / len(signals)

    def select_model(self, complexity_score: float) -> str:
        if self._powerful_model and complexity_score >= self._complexity_threshold:
            return self._powerful_model
        return self._cheap_model

    def fallback_model(self) -> str:
        """Always returns the cheap model. Called when the primary
        selection fails (e.g. `ModelUnavailableError`)."""
        return self._cheap_model

    def _has_comparison_keyword(self, lowered_query: str) -> bool:
        return any(keyword in lowered_query for keyword in _COMPARISON_KEYWORDS)

    def _multi_policy_signal(self, lowered_query: str) -> float:
        mentioned = sum(1 for keyword in _POLICY_TYPE_KEYWORDS if keyword in lowered_query)
        return min(mentioned / _MULTI_POLICY_SIGNAL_THRESHOLD, 1.0)

    def _length_signal(self, query_text: str) -> float:
        word_count = len(query_text.split())
        return min(word_count / _LONG_QUERY_WORD_THRESHOLD, 1.0)

    def _entity_count_signal(self, query_text: str) -> float:
        words = query_text.split()
        capitalized = sum(1 for word in words[1:] if word[:1].isupper())
        return min(capitalized / _ENTITY_SIGNAL_THRESHOLD, 1.0)
