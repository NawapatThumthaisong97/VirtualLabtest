#!/usr/bin/env python3
"""
Initialize database - create all tables
ใช้เพื่อสร้าง tables ทั้งหมดจากไฟล์ models
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from app.configs.db import Base, engine
from app import models  # noqa: F401

BASELINE_REVISION = "20261013_00"
RBAC_REVISION = "20261013_01"
QUOTA_RESERVATION_REVISION = "20261013_02"
LEGACY_TABLES = {
    "users",
    "courses",
    "announcements",
    "course_images",
    "enrollments",
    "lab_images",
    "quotas",
    "labs",
    "lab_progress",
    "sessions",
    "usage_records",
}
RBAC_TABLES = {"roles", "permissions", "user_roles", "role_permissions"}
RESERVATION_TABLE = "quota_reservations"


def init_database():
    print("Applying database migrations...")
    alembic_config = Config(str(backend_root / "alembic.ini"))
    existing_tables = set(inspect(engine).get_table_names())

    if "alembic_version" not in existing_tables:
        existing_legacy_tables = LEGACY_TABLES & existing_tables
        existing_rbac_tables = RBAC_TABLES & existing_tables
        has_reservations = "quota_reservations" in existing_tables

        if existing_legacy_tables and existing_legacy_tables != LEGACY_TABLES:
            raise RuntimeError(
                "Database has a partial legacy schema; refusing to stamp or create tables"
            )
        if existing_rbac_tables and existing_rbac_tables != RBAC_TABLES:
            raise RuntimeError(
                "Database has a partial RBAC schema; refusing to stamp or create tables"
            )
        if existing_legacy_tables == LEGACY_TABLES:
            schema_inspector = inspect(engine)
            tables_to_validate = LEGACY_TABLES | existing_rbac_tables
            if has_reservations:
                tables_to_validate.add(RESERVATION_TABLE)
            for table_name in tables_to_validate:
                expected_columns = set(Base.metadata.tables[table_name].columns.keys())
                actual_columns = {
                    column["name"]
                    for column in schema_inspector.get_columns(table_name)
                }
                repairable_columns = {
                    "courses": {"background_key", "icon_key"},
                    "lab_images": {
                        "cpu_requirement",
                        "memory_requirement",
                        "disk_size",
                        "lifespan_minutes",
                        "exposed_ports",
                        "entrypoint_script",
                        "workdir",
                        "env_vars",
                        "description",
                    },
                    "sessions": {"lab_image_id", "deleted_at"},
                    "user_roles": {"deleted_at"},
                    "role_permissions": {"is_seeded", "deleted_at"},
                }.get(table_name, set())
                missing_columns = expected_columns - actual_columns - repairable_columns
                if missing_columns:
                    raise RuntimeError(
                        f"Existing table {table_name} is missing columns "
                        f"{sorted(missing_columns)}; refusing to stamp migrations"
                    )

            if has_reservations and not existing_rbac_tables:
                raise RuntimeError(
                    "Quota reservations exist without the complete RBAC schema"
                )
            if has_reservations:
                reservation_columns = {
                    column["name"]
                    for column in schema_inspector.get_columns(RESERVATION_TABLE)
                }
                required_reservation_columns = set(
                    Base.metadata.tables[RESERVATION_TABLE].columns.keys()
                )
                if not required_reservation_columns.issubset(reservation_columns):
                    raise RuntimeError("Existing quota_reservations schema is incomplete")
            if has_reservations:
                command.stamp(alembic_config, QUOTA_RESERVATION_REVISION)
            elif existing_rbac_tables:
                command.stamp(alembic_config, RBAC_REVISION)
            else:
                command.stamp(alembic_config, BASELINE_REVISION)
        elif existing_tables:
            raise RuntimeError(
                "Database contains unrecognized tables; refusing automatic migration adoption"
            )

    command.upgrade(alembic_config, "head")
    print("Database schema is at Alembic head.")
    print("🔧 Initializing database...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully!")
    print("\n📊 Tables created:")
    print("  - users")
    print("  - courses")
    print("  - course_images")
    print("  - enrollments")
    print("  - labs")
    print("  - lab_images")
    print("  - lab_progress")
    print("  - sessions")
    print("  - usage_records")
    print("  - quotas")
    print("  - announcements")
    print("  - class_schedules")
    print("  - class_slots (+ extension btree_gist)")


if __name__ == "__main__":
    init_database()
