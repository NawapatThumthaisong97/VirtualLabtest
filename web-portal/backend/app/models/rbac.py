from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.configs.db import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("role_name", name="uq_roles_role_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint(
            "resource_domain", "permission_name", name="uq_permissions_domain_name"
        ),
        Index("ix_permissions_resource_domain", "resource_domain"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_domain = Column(String(100), nullable=False)
    permission_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class UserRoleAssignment(Base):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_id", "role_id"),)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (Index("ix_role_permissions_permission_id", "permission_id"),)

    role_id = Column(
        Integer,
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    permission_id = Column(
        Integer,
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )
    is_seeded = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)