from collections.abc import AsyncIterator
from uuid import uuid4

from core.domain.events import DomainEvent, GuardrailRejectionEvent
from core.ports.event_bus_port import EventBusPort, EventHandler
from core.ports.llm_port import LLMPort, UsageCost
from core.services.guardrails_service import GuardrailsService

_MODEL = "mock-cheap-model"


class FakeLLM(LLMPort):
    def __init__(self, response: str = "NO") -> None:
        self.response = response
        self.generate_calls: list[tuple[str, str]] = []

    async def generate(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> str:
        self.generate_calls.append((prompt, model))
        return self.response

    async def generate_stream(
        self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""  # pragma: no cover

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        raise NotImplementedError

    async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
        raise NotImplementedError


class FakeEventBus(EventBusPort):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError


def _service(
    llm: FakeLLM, bus: FakeEventBus, allowed_domains: frozenset[str] | None = None
) -> GuardrailsService:
    if allowed_domains is None:
        return GuardrailsService(llm, bus, cheap_model=_MODEL)
    return GuardrailsService(llm, bus, cheap_model=_MODEL, allowed_domains=allowed_domains)


async def test_query_with_an_allowed_keyword_is_accepted_without_an_llm_call() -> None:
    llm, bus = FakeLLM(), FakeEventBus()
    service = _service(llm, bus)

    result = await service.check("What's my dental deductible?", uuid4())

    assert result.allowed is True
    assert result.rejection_message is None
    assert llm.generate_calls == []
    assert bus.published == []


async def test_keyword_match_is_case_insensitive() -> None:
    llm, bus = FakeLLM(), FakeEventBus()
    service = _service(llm, bus)

    result = await service.check("Tell me about my COVERAGE options.", uuid4())

    assert result.allowed is True
    assert llm.generate_calls == []


async def test_general_benefits_question_is_accepted_without_an_llm_call() -> None:
    """Regression: "what benefits does <employer> offer?" names no specific
    sub-topic (dental/vision/etc.) and used to fall through to the LLM
    classifier, which sometimes misclassified it as off-topic."""
    llm, bus = FakeLLM(), FakeEventBus()
    service = _service(llm, bus)

    result = await service.check("What benefits does Acme Manufacturing offer?", uuid4())

    assert result.allowed is True
    assert llm.generate_calls == []


async def test_ambiguous_query_classified_on_topic_by_the_llm_is_accepted() -> None:
    llm, bus = FakeLLM(response="YES"), FakeEventBus()
    service = _service(llm, bus)

    result = await service.check("Am I able to add my new spouse?", uuid4())

    assert result.allowed is True
    assert len(llm.generate_calls) == 1
    prompt, model = llm.generate_calls[0]
    assert model == _MODEL
    assert "Am I able to add my new spouse?" in prompt


async def test_ambiguous_query_classified_off_topic_by_the_llm_is_rejected() -> None:
    employer_id = uuid4()
    llm, bus = FakeLLM(response="OFF_TOPIC"), FakeEventBus()
    service = _service(llm, bus)

    result = await service.check("Write me a python script.", employer_id)

    assert result.allowed is False
    assert result.rejection_message is not None
    assert "benefits" in result.rejection_message.lower()


async def test_rejection_publishes_a_guardrail_rejection_event() -> None:
    employer_id = uuid4()
    llm, bus = FakeLLM(response="OFF_TOPIC"), FakeEventBus()
    service = _service(llm, bus)

    await service.check("What's the weather like today?", employer_id)

    assert len(bus.published) == 1
    event = bus.published[0]
    assert isinstance(event, GuardrailRejectionEvent)
    assert event.employer_id == employer_id
    assert event.query_text == "What's the weather like today?"
    assert event.rejection_reason == "off_topic"


async def test_allowed_and_unparseable_llm_responses_allow() -> None:
    for response in ("ALLOWED", "allowed.", "NO", "yes", "maybe", "", "garbage ???"):
        llm, bus = FakeLLM(response=response), FakeEventBus()
        service = _service(llm, bus)

        result = await service.check("who is my employer", uuid4())

        assert result.allowed is True, f"expected acceptance for LLM response {response!r}"
        assert bus.published == []


async def test_off_topic_response_is_parsed_leniently() -> None:
    for response in ("off_topic", "Off-Topic.", "  OFF_TOPIC  ", "OFF TOPIC"):
        llm, bus = FakeLLM(response=response), FakeEventBus()
        service = _service(llm, bus)

        result = await service.check("Something ambiguous here.", uuid4())

        assert result.allowed is False, f"expected rejection for LLM response {response!r}"


async def test_history_is_included_in_the_classifier_prompt_truncated_and_limited() -> None:
    llm, bus = FakeLLM(response="ALLOWED"), FakeEventBus()
    service = _service(llm, bus)
    history = ["Employee: oldest turn"] + [f"Employee: turn {i}" for i in range(4)]
    history[-1] = "Assistant: " + "x" * 1000

    await service.check("what about my spouse?", uuid4(), history)

    prompt = llm.generate_calls[0][0]
    assert "oldest turn" not in prompt
    assert "Employee: turn 1" in prompt
    assert "x" * 289 in prompt and "x" * 301 not in prompt
    assert "what about my spouse?" in prompt


async def test_custom_allowed_domains_override_the_default_vocabulary() -> None:
    llm, bus = FakeLLM(), FakeEventBus()
    service = _service(llm, bus, allowed_domains=frozenset({"payroll"}))

    result = await service.check("Question about my payroll deductions.", uuid4())

    assert result.allowed is True
    assert llm.generate_calls == []


async def test_custom_allowed_domains_no_longer_match_the_default_keywords() -> None:
    llm, bus = FakeLLM(response="OFF_TOPIC"), FakeEventBus()
    service = _service(llm, bus, allowed_domains=frozenset({"payroll"}))

    result = await service.check("What's my dental deductible?", uuid4())

    assert len(llm.generate_calls) == 1
    assert result.allowed is False
