"""Abstraction over the vector database. Pinecone is Phase 3's adapter;
swapping to another vector DB means writing one new adapter, per
files/plan.md's hexagonal architecture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class VectorRecord:
    """A chunk's embedding plus the metadata needed to filter and trace it
    back to its source (employer_id, policy_id, doc_id, chunk_index,
    doc_version — see files/plan.md's ingestion flow)."""

    id: str
    values: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any]


class VectorStorePort(ABC):
    @abstractmethod
    async def upsert(self, namespace: str, records: list[VectorRecord]) -> None:
        """Insert or overwrite records by id, scoped to `namespace` (one
        namespace per employer, for hard tenant isolation)."""
        ...

    @abstractmethod
    async def query(
        self,
        namespace: str,
        vector: list[float],
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        """Semantic search within `namespace`, optionally filtered by
        metadata (e.g. policy_type)."""
        ...

    @abstractmethod
    async def delete_by_metadata(self, namespace: str, metadata_filter: dict[str, Any]) -> None:
        """Purge records matching a metadata filter — used for document
        version replacement (files/plan.md Step 7.2)."""
        ...
