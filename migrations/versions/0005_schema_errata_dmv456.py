"""Apply the 14 v0.3 schema errata DMV-4, DMV-5 and DMV-6.

Expand-only, in the order the earlier migrations use: columns and tables first,
then constraints and foreign keys, then triggers and privileges.  The ledger is
append-only, so this migration never rewrites existing history: where legacy
rows would contradict a new constraint it stops with a counted, explicit error
and leaves the resolution to a separate decision (`14 v0.3` §8).
"""

from alembic import op

revision = "0005_schema_errata"
down_revision = "0004_runtime_privileges"
branch_labels = None
depends_on = None

GENESIS_CHECK = """
        (case_version_before = 0
           AND case_version_after = 1
           AND from_state IS NULL
           AND to_state = 'INTAKE')
     OR (case_version_before > 0
           AND from_state IS NOT NULL
           AND case_version_after = case_version_before + 1)
"""


def upgrade() -> None:
    op.execute(
        f"""
        DO $dismissal$
        DECLARE
          orphans bigint;
        BEGIN
          SELECT count(*) INTO orphans FROM pre_experiment_dismissal;
          IF orphans > 0 THEN
            RAISE EXCEPTION
              'DMV-4: % pre_experiment_dismissal row(s) predate case_id and cannot be '
              'backfilled by this migration: the table is append-only. Resolve them '
              'under a separate decision before upgrading.', orphans
              USING ERRCODE = '55000';
          END IF;
        END
        $dismissal$;

        DO $genesis$
        DECLARE
          incompatible bigint;
          zero_version bigint;
        BEGIN
          SELECT count(*) INTO incompatible
            FROM state_transition
           WHERE NOT ({GENESIS_CHECK});
          SELECT count(*) INTO zero_version
            FROM state_transition
           WHERE case_version_before = 0
             AND NOT (case_version_after = 1 AND from_state IS NULL AND to_state = 'INTAKE');
          IF incompatible > 0 THEN
            RAISE EXCEPTION
              'DMV-5: % state_transition row(s) contradict the genesis check, % of them '
              'with case_version_before = 0. The ledger is append-only and this migration '
              'does not repair it: an existing case starts at case_version 1, so such rows '
              'come from the earlier test protocol and need a separate decision.',
              incompatible, zero_version
              USING ERRCODE = '55000';
          END IF;
        END
        $genesis$;

        ALTER TABLE pre_experiment_dismissal
          ADD COLUMN case_id uuid;
        ALTER TABLE pre_experiment_dismissal
          ADD CONSTRAINT ck_dismissal_case_uuid_v7 CHECK (pls_is_uuid_v7(case_id)),
          ADD CONSTRAINT fk_dismissal_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT uq_dismissal_case UNIQUE (case_id);
        ALTER TABLE pre_experiment_dismissal
          ALTER COLUMN case_id SET NOT NULL;

        ALTER TABLE state_transition
          ALTER COLUMN from_state DROP NOT NULL;
        ALTER TABLE state_transition
          ADD CONSTRAINT ck_transition_genesis CHECK ({GENESIS_CHECK});

        CREATE TABLE command_receipt (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          command_type text NOT NULL,
          idempotency_key text NOT NULL,
          case_id uuid CHECK (pls_is_uuid_v7(case_id)),
          actor_type text NOT NULL CHECK (actor_type IN ('user','system','timer','admin')),
          received_at timestamptz NOT NULL DEFAULT now(),
          outcome_ref text NOT NULL,
          outcome_kind text NOT NULL CHECK (outcome_kind IN ('applied','conflict','rejected')),
          UNIQUE (command_type, idempotency_key)
        );

        ALTER TABLE command_receipt
          ADD CONSTRAINT fk_command_receipt_case FOREIGN KEY (case_id) REFERENCES case_record(id);

        CREATE TRIGGER trg_command_receipt_append_only
          BEFORE UPDATE OR DELETE ON command_receipt
          FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();

        ALTER TABLE command_receipt OWNER TO pls_migrator;

        -- Commands are executed by the worker (architecture §1.1): web accepts the
        -- webhook and enqueues, so pls_web receives no privilege on this table.
        GRANT SELECT, INSERT ON TABLE command_receipt TO pls_worker;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
