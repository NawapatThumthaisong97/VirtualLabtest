from pydantic import Field

from app.schemas.base import CamelModel


class PermissionContext(CamelModel):
    permission_code: str = Field(
        min_length=3,
        max_length=260,
        pattern=r"^[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*){1,4}$",
    )
    resource_id: str | None = Field(default=None, min_length=1, max_length=255)

    @property
    def parts(self) -> tuple[str, str, str | None]:
        parts = self.permission_code.split(":")
        scopes = {"self", "assigned", "course", "global"}
        scope = parts[-1] if parts[-1] in scopes else None
        permission_parts = parts[1:-1] if scope is not None else parts[1:]
        return parts[0], ":".join(permission_parts), scope


class JWTClaims(CamelModel):
    user_id: str | None = None
    sub: str | None = None
    roles: list[str] = Field(default_factory=list)
    exp: int