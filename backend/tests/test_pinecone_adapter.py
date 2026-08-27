import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from pinecone.exceptions import ServiceException
from tenacity.wait import wait_exponential_jitter

from adapters.vector_store.pinecone_adapter import PineconeAdapter
from config import retry_config
from core.ports.vector_store_port import VectorMatch, VectorRecord, VectorStorePort


@dataclass
class _FakeMatch:
    id: str
    score: float
    metadata: dict[str, Any] | None = None


@dataclass
class _FakeQueryResponse:
    matches: list[_FakeMatch] = field(default_factory=list)


class _FakeIndex:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.upsert_side_effect: BaseException | None = None
        self.query_side_effect: BaseException | None = None
        self.delete_side_effect: BaseException | None = None
        self.query_return: _FakeQueryResponse = _FakeQueryResponse()

    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> None:
        self.upsert_calls.append({"vectors": vectors, "namespace": namespace})
        if self.upsert_side_effect is not None:
            raise self.upsert_side_effect

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        filter: dict[str, Any] | None,
        include_metadata: bool,
    ) -> _FakeQueryResponse:
        self.query_calls.append(
            {
                "vector": vector,
                "top_k": top_k,
                "namespace": namespace,
                "filter": filter,
                "include_metadata": include_metadata,
            }
        )
        if self.query_side_effect is not None:
            raise self.query_side_effect
        return self.query_return

    def delete(self, namespace: str, filter: dict[str, Any]) -> None:
        self.delete_calls.append({"namespace": namespace, "filter": filter})
        if self.delete_side_effect is not None:
            raise self.delete_side_effect


class _FakePineconeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.index = _FakeIndex()
        self.index_calls: list[str] = []

    def Index(self, name: str) -> _FakeIndex:  # noqa: N802 (matches the real SDK's method name)
        self.index_calls.append(name)
        return self.index


@pytest.fixture(autouse=True)
def _no_real_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _make_adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[PineconeAdapter, _FakePineconeClient]:
    fake_client_holder: dict[str, _FakePineconeClient] = {}

    def _fake_pinecone_ctor(api_key: str) -> _FakePineconeClient:
        client = _FakePineconeClient(api_key)
        fake_client_holder["client"] = client
        return client

    import adapters.vector_store.pinecone_adapter as module

    monkeypatch.setattr(module, "Pinecone", _fake_pinecone_ctor)
    adapter = PineconeAdapter(api_key="test-key", index_name="test-index")
    return adapter, fake_client_holder["client"]


def _service_unavailable() -> ServiceException:
    return ServiceException(status=503, reason="Service Unavailable")


def test_is_a_vector_store_port(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _make_adapter(monkeypatch)
    assert isinstance(adapter, VectorStorePort)


def test_upsert_retry_is_sourced_from_retry_config_not_hardcoded() -> None:
    retrying = PineconeAdapter.upsert.retry

    assert retrying.stop.max_attempt_number == retry_config.pinecone_max_attempts
    assert isinstance(retrying.wait, wait_exponential_jitter)
    assert retrying.wait.initial == retry_config.base_delay_seconds
    assert retrying.wait.max == retry_config.max_delay_seconds


async def test_upsert_resolves_the_index_by_name_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _make_adapter(monkeypatch)
    assert client.index_calls == []

    await adapter.upsert("employer-1", [])

    assert client.index_calls == ["test-index"]


async def test_upsert_reuses_the_resolved_index_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.upsert("employer-1", [])
    await adapter.query("employer-1", [0.1])

    assert client.index_calls == ["test-index"]


async def test_upsert_sends_vectors_with_id_values_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    record = VectorRecord(id="chunk-1", values=[0.1, 0.2], metadata={"employer_id": "emp-1"})

    await adapter.upsert("emp-1", [record])

    expected_vector = {"id": "chunk-1", "values": [0.1, 0.2], "metadata": {"employer_id": "emp-1"}}
    assert client.index.upsert_calls == [{"vectors": [expected_vector], "namespace": "emp-1"}]


async def test_upsert_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    call_count = 0
    original_upsert = client.index.upsert

    def _flaky_upsert(vectors: list[dict[str, Any]], namespace: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _service_unavailable()
        original_upsert(vectors, namespace)

    client.index.upsert = _flaky_upsert  # type: ignore[method-assign]

    await adapter.upsert("emp-1", [])

    assert call_count == 2


async def test_upsert_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.index.upsert_side_effect = _service_unavailable()

    with pytest.raises(ServiceException):
        await adapter.upsert("emp-1", [])

    assert len(client.index.upsert_calls) == 3


async def test_upsert_does_not_retry_a_non_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.index.upsert_side_effect = ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        await adapter.upsert("emp-1", [])

    assert len(client.index.upsert_calls) == 1


async def test_query_scopes_to_the_given_namespace_with_top_k_and_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.query("emp-1", [0.1, 0.2], top_k=3, metadata_filter={"policy_type": "dental"})

    assert client.index.query_calls == [
        {
            "vector": [0.1, 0.2],
            "top_k": 3,
            "namespace": "emp-1",
            "filter": {"policy_type": "dental"},
            "include_metadata": True,
        }
    ]


async def test_query_defaults_top_k_to_five_and_filter_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.query("emp-1", [0.1])

    call = client.index.query_calls[0]
    assert call["top_k"] == 5
    assert call["filter"] is None


async def test_query_maps_pinecone_matches_to_vector_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.index.query_return = _FakeQueryResponse(
        matches=[
            _FakeMatch(id="chunk-1", score=0.92, metadata={"section": "deductibles"}),
            _FakeMatch(id="chunk-2", score=0.81, metadata=None),
        ]
    )

    results = await adapter.query("emp-1", [0.1])

    assert results == [
        VectorMatch(id="chunk-1", score=0.92, metadata={"section": "deductibles"}),
        VectorMatch(id="chunk-2", score=0.81, metadata={}),
    ]


async def test_query_retries_on_a_retryable_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    expected = _FakeQueryResponse(matches=[_FakeMatch(id="chunk-1", score=0.5, metadata={})])
    call_count = 0

    def _flaky_query(**kwargs: Any) -> _FakeQueryResponse:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _service_unavailable()
        return expected

    client.index.query = _flaky_query  # type: ignore[method-assign]

    results = await adapter.query("emp-1", [0.1])

    assert call_count == 2
    assert results == [VectorMatch(id="chunk-1", score=0.5, metadata={})]


async def test_delete_by_metadata_scopes_to_namespace_and_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)

    await adapter.delete_by_metadata("emp-1", {"doc_id": "doc-123"})

    assert client.index.delete_calls == [{"namespace": "emp-1", "filter": {"doc_id": "doc-123"}}]


async def test_delete_by_metadata_gives_up_after_three_attempts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, client = _make_adapter(monkeypatch)
    client.index.delete_side_effect = _service_unavailable()

    with pytest.raises(ServiceException):
        await adapter.delete_by_metadata("emp-1", {"doc_id": "doc-123"})

    assert len(client.index.delete_calls) == 3
