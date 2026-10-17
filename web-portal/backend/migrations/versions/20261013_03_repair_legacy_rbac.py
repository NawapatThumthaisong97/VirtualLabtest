"""Repair RBAC metadata columns in schemas created before Alembic adoption.

Revision ID: 20261013_03
Revises: 20261013_02
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_03"
down_revision = "20261013_02"
branch_labels = None
depends_on = None


SEED_GRANTS = {
    "Student": (
        "clusters:create:self",
        "clusters:read:self",
        "clusters:delete:self",
        "kubernetes:cluster_admin:self",
        "network:tailscale:access:self",
        "storage:images:pull:self",
        "storage:images:push:self",
        "storage:data:read_write:self",
    ),
    "Instructor": (
        "clusters:create:course",
        "clusters:read:course",
        "clusters:update:course",
        "clusters:delete:course",
        "kubernetes:workloads:view:assigned",
        "kubernetes:workloads:exec:assigned",
        "kubernetes:workloads:logs:assigned",
        "network:tailscale:access:assigned",
        "storage:images:push:course",
        "storage:datasets:manage:course",
    ),
    "Admin": (
        "clusters:manage:global",
        "kubernetes:cluster_admin:global",
        "network:policies:manage:global",
        "network:tailscale:manage:global",
        "network:egress_allowlist:manage:global",
        "storage:r2:manage:global",
        "storage:registry:manage:global",
        "storage:quotas:manage:global",
    ),
}

REPAIR_TABLE = "_rbac_repair_20261013_03"


def upgrade() -> None:
    op.create_table(
        REPAIR_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("added_user_role_deleted_at", sa.Boolean(), nullable=False),
        sa.Column("added_role_permission_is_seeded", sa.Boolean(), nullable=False),
        sa.Column("added_role_permission_deleted_at", sa.Boolean(), nullable=False),
    )
    op.execute(
        """DO $$
        DECLARE
            add_user_role_deleted_at BOOLEAN;
            add_role_permission_is_seeded BOOLEAN;
            add_role_permission_deleted_at BOOLEAN;
        BEGIN
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'user_roles' AND column_name = 'deleted_at'
            ) INTO add_user_role_deleted_at;
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'role_permissions' AND column_name = 'is_seeded'
            ) INTO add_role_permission_is_seeded;
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'role_permissions' AND column_name = 'deleted_at'
            ) INTO add_role_permission_deleted_at;

            IF add_user_role_deleted_at THEN
                ALTER TABLE user_roles ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
            END IF;
            IF add_role_permission_is_seeded THEN
                ALTER TABLE role_permissions
                    ADD COLUMN is_seeded BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            IF add_role_permission_deleted_at THEN
                ALTER TABLE role_permissions ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
            END IF;

            INSERT INTO _rbac_repair_20261013_03 (
                id,
                added_user_role_deleted_at,
                added_role_permission_is_seeded,
                added_role_permission_deleted_at
            ) VALUES (
                1,
                add_user_role_deleted_at,
                add_role_permission_is_seeded,
                add_role_permission_deleted_at
            );
        END $$"""
    )

    seed_pairs = []
    for role_name, permission_codes in SEED_GRANTS.items():
        for permission_code in permission_codes:
            resource_domain, permission_name = permission_code.split(":", maxsplit=1)
            seed_pairs.append(
                f"('{role_name}', '{resource_domain}', '{permission_name}')"
            )
    op.execute(
        """UPDATE role_permissions AS rp
           SET is_seeded = TRUE
           FROM roles AS r, permissions AS p
           WHERE rp.role_id = r.id
             AND rp.permission_id = p.id
             AND (r.role_name, p.resource_domain, p.permission_name) IN (
                """ + ",\n                ".join(seed_pairs) + ")"
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        DECLARE
            repair_record RECORD;
        BEGIN
            IF to_regclass('_rbac_repair_20261013_03') IS NOT NULL THEN
                SELECT * INTO repair_record
                FROM _rbac_repair_20261013_03 WHERE id = 1;
                IF FOUND THEN
                    IF repair_record.added_role_permission_deleted_at THEN
                        ALTER TABLE role_permissions DROP COLUMN IF EXISTS deleted_at;
                    END IF;
                    IF repair_record.added_role_permission_is_seeded THEN
                        ALTER TABLE role_permissions DROP COLUMN IF EXISTS is_seeded;
                    END IF;
                    IF repair_record.added_user_role_deleted_at THEN
                        ALTER TABLE user_roles DROP COLUMN IF EXISTS deleted_at;
                    END IF;
                END IF;
                DROP TABLE _rbac_repair_20261013_03;
            END IF;
        END $$"""
    )