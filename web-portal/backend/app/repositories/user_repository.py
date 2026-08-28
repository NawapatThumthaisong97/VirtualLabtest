from sqlalchemy import or_, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def find_by_login(self, identifier: str) -> User | None:
        stmt = select(User).where(
            or_(User.student_id == identifier, User.email == identifier)
        )
        return self.db.execute(stmt).scalars().first()
