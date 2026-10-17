"""Repair known legacy application column drift without dropping old data.

Revision ID: 20261013_04
Revises: 20261013_03
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261013_04"
down_revision = "20261013_03"
branch_labels = None
depends_on = None

REPAIR_TABLE = "_legacy_repair_20261013_04"


def upgrade() -> None:
    op.create_table(
        REPAIR_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("added_columns", postgresql.JSONB(), nullable=False),
    )
    op.execute(
        """DO $$
        DECLARE
            added_columns JSONB := '{}'::jsonb;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'courses' AND column_name = 'background_key'
            ) THEN
                ALTER TABLE courses ADD COLUMN background_key VARCHAR(50);
                added_columns := added_columns || '{"courses.background_key": true}'::jsonb;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'courses' AND column_name = 'icon_key'
            ) THEN
                ALTER TABLE courses ADD COLUMN icon_key VARCHAR(50);
                added_columns := added_columns || '{"courses.icon_key": true}'::jsonb;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'cpu_requirement') THEN
                ALTER TABLE lab_images ADD COLUMN cpu_requirement VARCHAR(20) NOT NULL DEFAULT '2+';
                ALTER TABLE lab_images ALTER COLUMN cpu_requirement DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.cpu_requirement": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'memory_requirement') THEN
                ALTER TABLE lab_images ADD COLUMN memory_requirement VARCHAR(20) NOT NULL DEFAULT '4+';
                ALTER TABLE lab_images ALTER COLUMN memory_requirement DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.memory_requirement": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'disk_size') THEN
                ALTER TABLE lab_images ADD COLUMN disk_size INTEGER NOT NULL DEFAULT 50;
                ALTER TABLE lab_images ALTER COLUMN disk_size DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.disk_size": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'lifespan_minutes') THEN
                ALTER TABLE lab_images ADD COLUMN lifespan_minutes INTEGER NOT NULL DEFAULT 60;
                ALTER TABLE lab_images ALTER COLUMN lifespan_minutes DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.lifespan_minutes": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'exposed_ports') THEN
                ALTER TABLE lab_images ADD COLUMN exposed_ports JSONB NOT NULL DEFAULT '[]'::jsonb;
                ALTER TABLE lab_images ALTER COLUMN exposed_ports DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.exposed_ports": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'entrypoint_script') THEN
                ALTER TABLE lab_images ADD COLUMN entrypoint_script VARCHAR(255) NOT NULL DEFAULT '/bin/bash /run.sh';
                ALTER TABLE lab_images ALTER COLUMN entrypoint_script DROP DEFAULT;
                added_columns := added_columns || '{"lab_images.entrypoint_script": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'workdir') THEN
                ALTER TABLE lab_images ADD COLUMN workdir VARCHAR(255);
                added_columns := added_columns || '{"lab_images.workdir": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'env_vars') THEN
                ALTER TABLE lab_images ADD COLUMN env_vars JSONB;
                added_columns := added_columns || '{"lab_images.env_vars": true}'::jsonb;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'lab_images' AND column_name = 'description') THEN
                ALTER TABLE lab_images ADD COLUMN description TEXT;
                added_columns := added_columns || '{"lab_images.description": true}'::jsonb;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'sessions' AND column_name = 'lab_image_id'
            ) THEN
                ALTER TABLE sessions ADD COLUMN lab_image_id UUID;
                ALTER TABLE sessions
                    ADD CONSTRAINT fk_sessions_lab_image_id_lab_images
                    FOREIGN KEY (lab_image_id) REFERENCES lab_images (id) ON DELETE RESTRICT;
                added_columns := added_columns || '{"sessions.lab_image_id": true}'::jsonb;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'sessions' AND column_name = 'deleted_at'
            ) THEN
                ALTER TABLE sessions ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
                added_columns := added_columns || '{"sessions.deleted_at": true}'::jsonb;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'sessions' AND column_name = 'image_ref'
            ) THEN
                UPDATE sessions AS s
                SET lab_image_id = i.id
                FROM lab_images AS i
                WHERE s.lab_image_id IS NULL
                  AND s.image_ref = i.repository || ':' || i.tag;
            END IF;

            INSERT INTO _legacy_repair_20261013_04 (id, added_columns)
            VALUES (1, added_columns);
        END $$"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        DECLARE
            added_columns JSONB;
        BEGIN
            IF to_regclass('_legacy_repair_20261013_04') IS NOT NULL THEN
                SELECT repair.added_columns INTO added_columns
                FROM _legacy_repair_20261013_04 AS repair WHERE repair.id = 1;
                IF added_columns IS NOT NULL THEN
                    IF COALESCE((added_columns->>'sessions.lab_image_id')::boolean, FALSE) THEN
                        ALTER TABLE sessions DROP CONSTRAINT IF EXISTS fk_sessions_lab_image_id_lab_images;
                        ALTER TABLE sessions DROP COLUMN IF EXISTS lab_image_id;
                    END IF;
                    IF COALESCE((added_columns->>'sessions.deleted_at')::boolean, FALSE) THEN
                        ALTER TABLE sessions DROP COLUMN IF EXISTS deleted_at;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.description')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS description;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.env_vars')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS env_vars;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.workdir')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS workdir;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.entrypoint_script')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS entrypoint_script;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.exposed_ports')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS exposed_ports;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.lifespan_minutes')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS lifespan_minutes;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.disk_size')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS disk_size;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.memory_requirement')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS memory_requirement;
                    END IF;
                    IF COALESCE((added_columns->>'lab_images.cpu_requirement')::boolean, FALSE) THEN
                        ALTER TABLE lab_images DROP COLUMN IF EXISTS cpu_requirement;
                    END IF;
                    IF COALESCE((added_columns->>'courses.icon_key')::boolean, FALSE) THEN
                        ALTER TABLE courses DROP COLUMN IF EXISTS icon_key;
                    END IF;
                    IF COALESCE((added_columns->>'courses.background_key')::boolean, FALSE) THEN
                        ALTER TABLE courses DROP COLUMN IF EXISTS background_key;
                    END IF;
                END IF;
                DROP TABLE _legacy_repair_20261013_04;
            END IF;
        END $$"""
    )