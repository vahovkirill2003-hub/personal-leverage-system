"""Create database roles and shared invariant helpers."""

from alembic import op

revision = "0001_roles_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $roles$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pls_migrator') THEN
            CREATE ROLE pls_migrator NOLOGIN NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pls_web') THEN
            CREATE ROLE pls_web NOLOGIN NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pls_worker') THEN
            CREATE ROLE pls_worker NOLOGIN NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pls_scheduler') THEN
            CREATE ROLE pls_scheduler NOLOGIN NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pls_retention') THEN
            CREATE ROLE pls_retention NOLOGIN NOINHERIT;
          END IF;
        END
        $roles$;

        REVOKE CREATE ON SCHEMA public FROM PUBLIC;

        CREATE OR REPLACE FUNCTION pls_is_uuid_v7(value uuid)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        STRICT
        AS $function$
          SELECT (get_byte(uuid_send(value), 6) >> 4) = 7
             AND (get_byte(uuid_send(value), 8) >> 6) = 2
        $function$;

        CREATE OR REPLACE FUNCTION pls_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          RAISE EXCEPTION '% is append-only: % is forbidden', TG_TABLE_NAME, TG_OP
            USING ERRCODE = '55000';
        END
        $function$;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
