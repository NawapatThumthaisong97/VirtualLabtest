from sqlalchemy import func, or_, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def find_by_login(self, identifier: str) -> User | None:
        normalized = identifier.strip()
        stmt = select(User).where(
            or_(
                User.student_id == normalized,
                func.lower(User.email) == normalized.lower(),
            )
        )
        return self.db.execute(stmt).scalars().first()

    def find_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        stmt = select(User).where(func.lower(User.email) == normalized)
        return self.db.execute(stmt).scalars().first()
