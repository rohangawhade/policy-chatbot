"""Determines whether a query is about employee benefits before any
retrieval or expensive LLM generation happens (files/plan.md Step 6.1).

Off-topic queries never reach Pinecone or the powerful/generation model
tier — the whole point of this service existing.
"""

from dataclasses import dataclass
from uuid import UUID

from core.domain.events import GuardrailRejectionEvent
from core.ports.event_bus_port import EventBusPort
from core.ports.llm_port import LLMPort

_REJECTION_REASON = "off_topic"
_REJECTION_MESSAGE = (
    "I can only help with questions about your benefits — health, dental, "
    "vision, life, disability, enrollment, coverage, and claims. Could you "
    "rephrase your question around one of those topics?"
)
_DEFAULT_ALLOWED_DOMAINS = frozenset(
    {"health", "dental", "vision", "life", "disability", "enrollment", "coverage", "claims"}
)
_CLASSIFICATION_MAX_TOKENS = 5
_CLASSIFICATION_PROMPT = (
    "You are a strict binary classifier for an employee benefits chatbot. "
    "Reply with exactly one word: YES or NO. Do not explain.\n\n"
    "Is the following question about one of these employee benefits topics: "
    "{domains}?\n\nQuestion: {query}"
)


@dataclass(frozen=True, kw_only=True)
class GuardrailResult:
    """Whether a query is allowed through to retrieval/generation.

    Attributes:
        allowed: True if the query may proceed.
        rejection_message: A ready-to-display message when `allowed` is
            False; `None` when `allowed` is True.
    """

    allowed: bool
    rejection_message: str | None = None


class GuardrailsService:
    """Classifies a query as in-domain or off-topic.

    Keyword matching is the fast, free path — any query containing an
    allowed-domain word is accepted immediately, no LLM call. Everything
    else is ambiguous and gets one cheap-model classification call
    before being rejected — still far cheaper than a full retrieval +
    generation round trip through the powerful model tier.

    Every rejection is published as a `GuardrailRejectionEvent`
    (`files/coding-standards.md` section 12: analytics logging is
    fire-and-forget via the event bus, never a direct blocking write on
    the request path). `api/event_subscribers.py`'s
    `register_default_subscribers()` (wired into `get_event_bus()`)
    persists it as a `GuardrailRejection` row — this service itself never
    touches `AnalyticsRepository` directly, keeping the Postgres write
    out of the guardrail check's own call path.

    Attributes:
        llm: Used only for the cheap-model classification call.
        event_bus: Publishes `GuardrailRejectionEvent` on every rejection.
        cheap_model: Model name for the classification call — this
            service has no opinion on which model is configured, same
            pattern as every other Phase 3/4 adapter.
        allowed_domains: Keyword vocabulary defining what's in-domain.
    """

    def __init__(
        self,
        llm: LLMPort,
        event_bus: EventBusPort,
        cheap_model: str,
        allowed_domains: frozenset[str] = _DEFAULT_ALLOWED_DOMAINS,
    ) -> None:
        self._llm = llm
        self._event_bus = event_bus
        self._cheap_model = cheap_model
        self._allowed_domains = allowed_domains

    async def check(self, query_text: str, employer_id: UUID) -> GuardrailResult:
        """Classify `query_text`, rejecting and logging it if off-topic."""
        if self._matches_allowed_domain(query_text):
            return GuardrailResult(allowed=True)
        if await self._classify_on_topic(query_text):
            return GuardrailResult(allowed=True)

        await self._event_bus.publish(
            GuardrailRejectionEvent(
                employer_id=employer_id,
                query_text=query_text,
                rejection_reason=_REJECTION_REASON,
            )
        )
        return GuardrailResult(allowed=False, rejection_message=_REJECTION_MESSAGE)

    def _matches_allowed_domain(self, query_text: str) -> bool:
        lowered = query_text.lower()
        return any(domain in lowered for domain in self._allowed_domains)

    async def _classify_on_topic(self, query_text: str) -> bool:
        prompt = _CLASSIFICATION_PROMPT.format(
            domains=", ".join(sorted(self._allowed_domains)), query=query_text
        )
        response = await self._llm.generate(
            prompt,
            model=self._cheap_model,
            temperature=0.0,
            max_tokens=_CLASSIFICATION_MAX_TOKENS,
        )
        return response.strip().upper().startswith("YES")
