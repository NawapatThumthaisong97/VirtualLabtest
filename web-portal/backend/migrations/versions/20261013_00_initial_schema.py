"""Baseline the existing VirtualLab schema.

Revision ID: 20261013_00
Revises:
Create Date: 2026-10-13
"""

from alembic import op


revision = "20261013_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "CREATE TYPE userrole AS ENUM ('STUDENT', 'INSTRUCTOR', 'ADMIN')",
        "CREATE TYPE roleincourse AS ENUM ('STUDENT', 'TA', 'INSTRUCTOR')",
        "CREATE TYPE imagestatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED')",
        "CREATE TYPE quotaperiod AS ENUM ('WEEKLY', 'MONTHLY', 'SEMESTER')",
        "CREATE TYPE labstatus AS ENUM ('DRAFT', 'PUBLISHED')",
        "CREATE TYPE progressstatus AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'FINISHED')",
        "CREATE TYPE servicetype AS ENUM ('LAB', 'COMPUTE_SERVICE', 'AI_TRAINING')",
        "CREATE TYPE sessionstatus AS ENUM ('PENDING', 'RUNNING', 'STOPPED', 'FAILED')",
        """CREATE TABLE users (
            id UUID NOT NULL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            student_id VARCHAR(50),
            password_hash VARCHAR(255),
            role userrole NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
        )""",
        "CREATE INDEX ix_users_id ON users (id)",
        "CREATE UNIQUE INDEX ix_users_student_id ON users (student_id)",
        "CREATE UNIQUE INDEX ix_users_email ON users (email)",
        """CREATE TABLE courses (
            id UUID NOT NULL PRIMARY KEY,
            code VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            lecturer_name VARCHAR(255) NOT NULL,
            image_url VARCHAR(2048),
            background_key VARCHAR(50),
            icon_key VARCHAR(50),
            created_by UUID NOT NULL REFERENCES users (id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            deleted_at TIMESTAMP WITH TIME ZONE
        )""",
        "CREATE INDEX ix_courses_deleted_at ON courses (deleted_at)",
        "CREATE UNIQUE INDEX ix_courses_code ON courses (code)",
        "CREATE INDEX ix_courses_id ON courses (id)",
        """CREATE TABLE announcements (
            id UUID NOT NULL PRIMARY KEY,
            course_id UUID REFERENCES courses (id),
            author_id UUID NOT NULL REFERENCES users (id),
            message TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
        )""",
        "CREATE INDEX ix_announcements_course_id ON announcements (course_id)",
        "CREATE INDEX ix_announcements_id ON announcements (id)",
        """CREATE TABLE course_images (
            id UUID NOT NULL PRIMARY KEY,
            course_id UUID NOT NULL REFERENCES courses (id),
            image_url VARCHAR(2048) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            created_by UUID NOT NULL REFERENCES users (id)
        )""",
        "CREATE UNIQUE INDEX ix_course_images_course_id ON course_images (course_id)",
        "CREATE INDEX ix_course_images_id ON course_images (id)",
        """CREATE TABLE enrollments (
            user_id UUID NOT NULL REFERENCES users (id),
            course_id UUID NOT NULL REFERENCES courses (id),
            role_in_course roleincourse NOT NULL,
            enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (user_id, course_id)
        )""",
        """CREATE TABLE lab_images (
            id UUID NOT NULL PRIMARY KEY,
            uploaded_by UUID NOT NULL REFERENCES users (id),
            course_id UUID NOT NULL REFERENCES courses (id),
            repository VARCHAR(255) NOT NULL,
            tag VARCHAR(100) NOT NULL,
            image_digest VARCHAR(255) NOT NULL UNIQUE,
            size_mb INTEGER NOT NULL,
            cpu_requirement VARCHAR(20) NOT NULL,
            memory_requirement VARCHAR(20) NOT NULL,
            disk_size INTEGER NOT NULL,
            lifespan_minutes INTEGER NOT NULL,
            exposed_ports JSONB NOT NULL,
            entrypoint_script VARCHAR(255) NOT NULL,
            workdir VARCHAR(255),
            env_vars JSONB,
            description TEXT,
            status imagestatus NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT uq_repository_tag UNIQUE (repository, tag)
        )""",
        "CREATE INDEX ix_lab_images_course_id ON lab_images (course_id)",
        "CREATE INDEX ix_lab_images_id ON lab_images (id)",
        """CREATE TABLE quotas (
            id UUID NOT NULL PRIMARY KEY,
            user_id UUID REFERENCES users (id),
            course_id UUID REFERENCES courses (id),
            compute_hours_limit NUMERIC(10, 2) NOT NULL,
            storage_mb_limit INTEGER NOT NULL,
            period quotaperiod NOT NULL
        )""",
        "CREATE INDEX ix_quotas_id ON quotas (id)",
        """CREATE TABLE labs (
            id UUID NOT NULL PRIMARY KEY,
            course_id UUID NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            order_no INTEGER NOT NULL,
            description TEXT,
            doc_url VARCHAR(500),
            image_id UUID REFERENCES lab_images (id) ON DELETE RESTRICT,
            due_at TIMESTAMP WITH TIME ZONE,
            status labstatus NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE,
            deleted_at TIMESTAMP WITH TIME ZONE
        )""",
        "CREATE INDEX ix_labs_deleted_at ON labs (deleted_at)",
        "CREATE INDEX ix_labs_course_id ON labs (course_id)",
        "CREATE INDEX ix_labs_id ON labs (id)",
        "CREATE UNIQUE INDEX unique_course_order ON labs (course_id, order_no) WHERE deleted_at IS NULL",
        """CREATE TABLE lab_progress (
            user_id UUID NOT NULL REFERENCES users (id),
            lab_id UUID NOT NULL REFERENCES labs (id),
            status progressstatus NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            finished_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (user_id, lab_id)
        )""",
        """CREATE TABLE sessions (
            id UUID NOT NULL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users (id),
            lab_id UUID REFERENCES labs (id),
            lab_image_id UUID REFERENCES lab_images (id),
            service_type servicetype NOT NULL,
            k8s_pod_name VARCHAR(255),
            node_name VARCHAR(255),
            is_remote BOOLEAN NOT NULL,
            is_cloud BOOLEAN NOT NULL,
            sky_cluster_name VARCHAR(255),
            sky_job_id INTEGER,
            endpoints JSONB,
            status sessionstatus NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            deleted_at TIMESTAMP WITH TIME ZONE
        )""",
        "CREATE INDEX ix_sessions_deleted_at ON sessions (deleted_at)",
        "CREATE INDEX ix_sessions_id ON sessions (id)",
        "CREATE INDEX ix_sessions_user_id ON sessions (user_id)",
        """CREATE TABLE usage_records (
            id BIGSERIAL NOT NULL PRIMARY KEY,
            session_id UUID NOT NULL REFERENCES sessions (id),
            cpu_seconds BIGINT NOT NULL,
            gpu_seconds BIGINT NOT NULL,
            ram_mb_hours NUMERIC(12, 2) NOT NULL,
            is_cloud_burst BOOLEAN NOT NULL,
            est_cost_thb NUMERIC(10, 2) NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
        )""",
        "CREATE INDEX ix_usage_records_session_id ON usage_records (session_id)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    statements = (
        "DROP TABLE usage_records",
        "DROP TABLE sessions",
        "DROP TABLE lab_progress",
        "DROP TABLE labs",
        "DROP TABLE quotas",
        "DROP TABLE lab_images",
        "DROP TABLE enrollments",
        "DROP TABLE course_images",
        "DROP TABLE announcements",
        "DROP TABLE courses",
        "DROP TABLE users",
        "DROP TYPE sessionstatus",
        "DROP TYPE servicetype",
        "DROP TYPE progressstatus",
        "DROP TYPE labstatus",
        "DROP TYPE quotaperiod",
        "DROP TYPE imagestatus",
        "DROP TYPE roleincourse",
        "DROP TYPE userrole",
    )
    for statement in statements:
        op.execute(statement)