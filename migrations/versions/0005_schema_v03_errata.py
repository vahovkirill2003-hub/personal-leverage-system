"""Migrate the schema to `14 v0.3` errata DMV-4, DMV-5 and DMV-6 (TB-04a).

Three technical errata of `14 v0.3` §17 change the schema and are applied here
in the expand/contract order of §8: every step is additive or a relaxation, no
step drops a column, and no step is destructive, so the release-step can run
before the application switches over.

`DMV-4` makes `pre_experiment_dismissal.case_id` the canonical mark of an
administrative dismissal (`14 v0.3` §3.1, §5 п. 12); `DMV-5` admits
`state_transition.from_state IS NULL` for the genesis transition alone and
fences every other transition with a CHECK (§3.3, §5 п. 13); `DMV-6` introduces
`command_receipt` as the transport-independent carrier of command idempotency
with `pls_worker`-only privileges (§3.3, §4, §5 п. 14, §12).

The genesis CHECK is added validated, not `NOT VALID`: a row written under the
previous schema with `case_version_before = 0` and a non-null `from_state` is
exactly the state the erratum forbids, and letting it survive behind an
unvalidated constraint would keep the invariant unenforced for that row. Such a
migration fails loudly, and the fix is forward (§8), never a weakened check.
"""

from alembic import op

revision = "0005_schema_v03_errata"
down_revision = "0004_runtime_privileges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        -- DMV-4: expand with a nullable column, then contract to NOT NULL.
        -- `pre_experiment_dismissal` is append-only, so a row that predates the
        -- erratum could not be backfilled by any authorized path; the schema
        -- refuses to contract over one instead of inventing an owner for it.
        ALTER TABLE pre_experiment_dismissal ADD COLUMN case_id uuid;

        DO $backfill$
        BEGIN
          IF EXISTS (SELECT 1 FROM pre_experiment_dismissal WHERE case_id IS NULL) THEN
            RAISE EXCEPTION
              'pre_experiment_dismissal has rows without case_id; DMV-4 cannot be backfilled on an append-only table'
              USING ERRCODE = '55000';
          END IF;
        END
        $backfill$;

        ALTER TABLE pre_experiment_dismissal
          ALTER COLUMN case_id SET NOT NULL,
          ADD CONSTRAINT ck_dismissal_case_uuid_v7 CHECK (pls_is_uuid_v7(case_id)),
          ADD CONSTRAINT fk_dismissal_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT uq_dismissal_case UNIQUE (case_id);

        -- DMV-5: genesis is the only transition without a source state.
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

        -- DMV-6: domain idempotency of every command of the `17 v0.2` §1.2 registry.
        CREATE TABLE command_receipt (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          command_type text NOT NULL,
          idempotency_key text NOT NULL,
          case_id uuid CHECK (case_id IS NULL OR pls_is_uuid_v7(case_id)),
          actor_type text NOT NULL CHECK (actor_type IN ('user','system','agent_run','timer','admin')),
          received_at timestamptz NOT NULL DEFAULT now(),
          outcome_ref text NOT NULL,
          outcome_kind text NOT NULL CHECK (outcome_kind IN ('applied','conflict','rejected')),
          CONSTRAINT uq_command_receipt_key UNIQUE (command_type, idempotency_key),
          CONSTRAINT fk_command_receipt_case FOREIGN KEY (case_id) REFERENCES case_record(id)
        );

        CREATE TRIGGER trg_command_receipt_append_only
          BEFORE UPDATE OR DELETE ON command_receipt
          FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();

        ALTER TABLE command_receipt OWNER TO pls_migrator;

        -- `14 v0.3` §12: the worker executes commands and therefore reads the
        -- stored outcome and writes a new receipt.  UPDATE and DELETE are not
        -- granted and are additionally refused by the append-only trigger.  The
        -- web process executes no command and receives no privilege at all.
        GRANT SELECT, INSERT ON TABLE command_receipt TO pls_worker;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
