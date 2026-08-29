from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, id: Any) -> T | None:
        stmt = select(self.model).where(self.model.id == id)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[T]:
        stmt = select(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return list(self.db.execute(stmt).scalars().all())

    def save(self, entity: T) -> T:
        self.db.add(entity)
        self.db.flush()
        return entity

    def soft_delete(self, entity: T) -> None:
        entity.deleted_at = datetime.now(timezone.utc)
        self.db.flush()

    def hard_delete(self, entity: T) -> None:
        self.db.delete(entity)
        self.db.flush()