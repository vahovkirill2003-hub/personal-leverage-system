"""Apply data-model v0.3 schema errata DMV-4, DMV-5, and DMV-6.

Owner task: TB-04a (`25 v0.2`).  Source: `14 v0.3` §17 plus §§3.1, 3.3, 4, 5, 8, 12.

The migration follows the expand/contract policy of `14 v0.3` §8: every step is
backward compatible for readers of the previous schema, and no destructive
change is performed.  `pre_experiment_dismissal.case_id` is added nullable
first, then tightened, so the release step never rewrites a table that a running
process could still be writing under the old contract.

Both new CHECK constraints are added validated, not `NOT VALID`: an
unvalidated constraint would leave the invariants of `14 v0.3` §5 п. 12–14
unenforced for rows already present, which is exactly the guarantee the errata
exist to provide.
"""

from alembic import op

revision = "0005_schema_errata_v03"
down_revision = "0004_runtime_privileges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DMV-4 — expand: the canonical marker of an administrative dismissal gains
    # its case reference.  Added nullable so the column exists before it is
    # required; backfill is impossible for rows written under the old contract,
    # because the schema recorded no case reference to recover, so the migration
    # stops instead of inventing one.
    op.execute(
        r"""
        ALTER TABLE pre_experiment_dismissal ADD COLUMN case_id uuid;

        DO $$
        DECLARE orphans bigint;
        BEGIN
          SELECT count(*) INTO orphans FROM pre_experiment_dismissal WHERE case_id IS NULL;
          IF orphans > 0 THEN
            RAISE EXCEPTION
              'DMV-4 backfill impossible: % pre_experiment_dismissal row(s) predate case_id', orphans;
          END IF;
        END
        $$;

        ALTER TABLE pre_experiment_dismissal
          ALTER COLUMN case_id SET NOT NULL,
          ADD CONSTRAINT ck_pre_experiment_dismissal_case_uuid_v7 CHECK (pls_is_uuid_v7(case_id)),
          ADD CONSTRAINT fk_pre_experiment_dismissal_case
            FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT uq_pre_experiment_dismissal_case UNIQUE (case_id);
        """
    )

    # DMV-5 — genesis transition.  `from_state` becomes nullable and the CHECK
    # of `14 v0.3` §3.3 keeps the state machine closed: NULL is admissible only
    # for the creation transition, every other transition keeps a source state
    # and advances the version by exactly one.
    op.execute(
        r"""
        ALTER TABLE state_transition ALTER COLUMN from_state DROP NOT NULL;

        ALTER TABLE state_transition
          ADD CONSTRAINT ck_state_transition_genesis CHECK (
            (case_version_before = 0
              AND case_version_after = 1
              AND from_state IS NULL
              AND to_state = 'INTAKE')
            OR
            (case_version_before > 0
              AND from_state IS NOT NULL
              AND case_version_after = case_version_before + 1)
          );
        """
    )

    # DMV-6 — transport-independent command idempotency register.
    op.execute(
        r"""
        CREATE TABLE command_receipt (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          command_type text NOT NULL,
          idempotency_key text NOT NULL,
          case_id uuid CHECK (case_id IS NULL OR pls_is_uuid_v7(case_id)),
          actor_type text NOT NULL CHECK (actor_type IN ('user','system','agent_run','timer','admin')),
          received_at timestamptz NOT NULL DEFAULT now(),
          outcome_ref text NOT NULL,
          outcome_kind text NOT NULL CHECK (outcome_kind IN ('applied','conflict','rejected')),
          CONSTRAINT fk_command_receipt_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          CONSTRAINT uq_command_receipt_idempotency UNIQUE (command_type, idempotency_key)
        );

        CREATE TRIGGER trg_command_receipt_append_only
          BEFORE UPDATE OR DELETE ON command_receipt
          FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();

        ALTER TABLE command_receipt OWNER TO pls_migrator;
        REVOKE ALL ON TABLE command_receipt FROM PUBLIC;

        -- `14 v0.3` §12: the worker executes commands and therefore reads a
        -- stored outcome and writes a new receipt.  UPDATE and DELETE are never
        -- granted, and the append-only trigger rejects them regardless.  `pls_web`
        -- receives no privilege at all — it enqueues, it does not execute.
        GRANT SELECT, INSERT ON TABLE command_receipt TO pls_worker;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
