from collections.abc import AsyncIterator
from typing import Any

import pytest

from core.ports.cache_port import CachePort
from core.ports.document_processor_port import DocumentProcessorPort
from core.ports.event_bus_port import EventBusPort
from core.ports.llm_port import LLMPort, UsageCost
from core.ports.vector_store_port import VectorMatch, VectorRecord, VectorStorePort


def test_llm_port_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        LLMPort()  # type: ignore[abstract]


async def test_llm_port_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeLLM(LLMPort):
        async def generate(
            self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
        ) -> str:
            return f"response to: {prompt}"

        async def generate_stream(
            self, prompt: str, *, model: str, temperature: float = 0.1, max_tokens: int = 2048
        ) -> AsyncIterator[str]:
            for token in ["hello", " ", "world"]:
                yield token

        async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        async def estimate_cost(self, model: str, prompt: str, completion: str) -> UsageCost:
            return UsageCost(input_tokens=1, output_tokens=1, estimated_cost_usd=0.0)

    llm = _FakeLLM()

    assert await llm.generate("hi", model="test-model") == "response to: hi"
    tokens = [t async for t in llm.generate_stream("hi", model="test-model")]
    assert tokens == ["hello", " ", "world"]
    assert await llm.embed(["a", "b"], model="test-embed") == [[0.1, 0.2], [0.1, 0.2]]
    assert await llm.estimate_cost("test-model", "hi", "hello") == UsageCost(
        input_tokens=1, output_tokens=1, estimated_cost_usd=0.0
    )


def test_vector_record_and_match_are_frozen() -> None:
    record = VectorRecord(id="chunk-1", values=[0.1, 0.2], metadata={"employer_id": "emp_1"})
    match = VectorMatch(id="chunk-1", score=0.95, metadata={"employer_id": "emp_1"})

    with pytest.raises(AttributeError):
        record.id = "chunk-2"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        match.score = 0.5  # type: ignore[misc]


async def test_vector_store_port_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeVectorStore(VectorStorePort):
        def __init__(self) -> None:
            self.upserted: list[VectorRecord] = []

        async def upsert(self, namespace: str, records: list[VectorRecord]) -> None:
            self.upserted.extend(records)

        async def query(
            self,
            namespace: str,
            vector: list[float],
            *,
            top_k: int = 5,
            metadata_filter: dict[str, Any] | None = None,
        ) -> list[VectorMatch]:
            return [VectorMatch(id=r.id, score=1.0, metadata=r.metadata) for r in self.upserted]

        async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
            self.upserted.clear()

    store = _FakeVectorStore()
    record = VectorRecord(id="c1", values=[0.1], metadata={"employer_id": "emp_1"})
    await store.upsert("emp_1", [record])

    matches = await store.query("emp_1", [0.1], top_k=5)
    assert matches == [VectorMatch(id="c1", score=1.0, metadata={"employer_id": "emp_1"})]

    await store.delete_by_metadata("emp_1", {"employer_id": "emp_1"})
    assert store.upserted == []


async def test_event_bus_port_concrete_implementation_satisfies_the_contract() -> None:
    from core.domain.events import DomainEvent

    class _FakeEventBus(EventBusPort):
        def __init__(self) -> None:
            self.published: list[DomainEvent] = []
            self.handlers: dict[str, list[Any]] = {}

        async def publish(self, event: DomainEvent) -> None:
            self.published.append(event)

        def subscribe(self, event_type: str, handler: Any) -> None:
            self.handlers.setdefault(event_type, []).append(handler)

        def unsubscribe(self, event_type: str, handler: Any) -> None:
            self.handlers.get(event_type, []).remove(handler)

    bus = _FakeEventBus()
    handler = lambda event: None  # noqa: E731
    bus.subscribe("test.event", handler)
    await bus.publish(DomainEvent(event_type="test.event"))
    bus.unsubscribe("test.event", handler)

    assert len(bus.published) == 1
    assert bus.handlers["test.event"] == []


async def test_cache_port_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeCache(CachePort):
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.store.get(key)

        async def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
            self.store[key] = value

        async def delete(self, key: str) -> None:
            self.store.pop(key, None)

        async def exists(self, key: str) -> bool:
            return key in self.store

        async def delete_by_prefix(self, prefix: str) -> None:
            for key in [key for key in self.store if key.startswith(prefix)]:
                del self.store[key]

    cache = _FakeCache()
    await cache.set("k", "v")
    assert await cache.get("k") == "v"
    assert await cache.exists("k") is True

    await cache.delete("k")
    assert await cache.get("k") is None
    assert await cache.exists("k") is False

    await cache.set("prefix:a", "1")
    await cache.set("prefix:b", "2")
    await cache.set("other:c", "3")
    await cache.delete_by_prefix("prefix:")
    assert await cache.get("prefix:a") is None
    assert await cache.get("prefix:b") is None
    assert await cache.get("other:c") == "3"


def test_document_processor_port_concrete_implementation_satisfies_the_contract() -> None:
    class _FakeProcessor(DocumentProcessorPort):
        def extract_text(self, file_path: str) -> str:
            return f"text of {file_path}"

        def extract_metadata(self, file_path: str) -> dict[str, Any]:
            return {"pages": 1}

    processor = _FakeProcessor()

    assert processor.extract_text("doc.pdf") == "text of doc.pdf"
    assert processor.extract_metadata("doc.pdf") == {"pages": 1}
