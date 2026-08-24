"""Generic SQLAlchemy Unit-of-Work repository base.

Implements the four `RepositoryPort[T]` methods (get/create/update/
delete) once; concrete repositories only supply `_to_orm`/`_to_domain`/
`_apply_update` (entity-specific — mainly because ORM enum columns store
each member's `.name`, e.g. `"ADMIN"`, while a domain enum member's
`.value` is what pydantic round-trips on read, e.g. `"admin"` — see
`files/plan.md` Step 1.3's ENUM LIFECYCLE note for the DB-level half of
this) plus whatever extra query methods their own port adds.

The session is injected, never owned, and this class never calls
`session.commit()` — "a single session per request, committed at the
API layer" (files/plan.md Step 3.5). It does call `session.flush()` so a
generated id or server-side default is visible on the returned domain
object without waiting for the request to end.
"""

from abc import ABC, abstractmethod
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class _HasId(Protocol):
    id: UUID


DomainT = TypeVar("DomainT", bound=_HasId)
OrmT = TypeVar("OrmT")


class PostgresRepository(ABC, Generic[DomainT, OrmT]):
    def __init__(self, session: AsyncSession, orm_model: type[OrmT]) -> None:
        self._session = session
        self._orm_model = orm_model

    @abstractmethod
    def _to_orm(self, entity: DomainT) -> OrmT:
        """Build a new, transient ORM instance from a domain entity."""
        ...

    @abstractmethod
    def _to_domain(self, orm_obj: OrmT) -> DomainT:
        """`Domain.model_validate(orm_obj)` — pydantic's `from_attributes`
        (Step 2.1) handles the mapping, including enum coercion by value,
        so this is one line in every concrete repository."""
        ...

    @abstractmethod
    def _apply_update(self, existing: OrmT, entity: DomainT) -> None:
        """Copy every mutable field from `entity` onto the persistent
        `existing` ORM instance — never `id`, never `created_at`."""
        ...

    async def get(self, entity_id: UUID) -> DomainT | None:
        orm_obj = await self._session.get(self._orm_model, entity_id)
        return self._to_domain(orm_obj) if orm_obj is not None else None

    async def create(self, entity: DomainT) -> DomainT:
        orm_obj = self._to_orm(entity)
        self._session.add(orm_obj)
        await self._session.flush()
        await self._session.refresh(orm_obj)
        return self._to_domain(orm_obj)

    async def update(self, entity: DomainT) -> DomainT:
        existing = await self._session.get(self._orm_model, entity.id)
        if existing is None:
            raise ValueError(f"{self._orm_model.__name__} {entity.id} does not exist")
        self._apply_update(existing, entity)
        await self._session.flush()
        await self._session.refresh(existing)
        return self._to_domain(existing)

    async def delete(self, entity_id: UUID) -> None:
        orm_obj = await self._session.get(self._orm_model, entity_id)
        if orm_obj is None:
            return
        await self._session.delete(orm_obj)
        await self._session.flush()
