"""Apply least-privilege runtime roles after all schema objects exist."""

from alembic import op

revision = "0004_runtime_privileges"
down_revision = "0003_invariants"
branch_labels = None
depends_on = None

TABLES = (
    "case_record, experiment_anchor, active_experiment_slot, pre_experiment_dismissal, "
    "dossier, dossier_revision, area_record, carry_forward, event, state_transition, inbox, outbox, "
    "gate_attempt, gate_review_session, coverage_cell, finding, gate_record, defect, decision_intent, "
    "consent, authority_grant, expense, external_action, workload_ledger, fact_record, evidence, artifact, "
    "late_evidence, linked_case, evidence_retention_policy, timer, preparation_interval, time_grant, "
    "context_package, agent_run, model_call, cost_record, price_catalog, data_policy_registry, cost_envelope, "
    "closure, decision_update, condition_record, review_stop_record, cycle_review_record"
)


def upgrade() -> None:
    op.execute(
        f"""
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
        REVOKE CREATE ON SCHEMA public FROM PUBLIC;

        GRANT USAGE ON SCHEMA public TO pls_web, pls_worker, pls_scheduler, pls_retention;
        GRANT EXECUTE ON FUNCTION pls_is_uuid_v7(uuid) TO pls_worker, pls_scheduler;

        GRANT SELECT ON TABLE
          case_record, active_experiment_slot, dossier, dossier_revision, area_record,
          outbox, timer, tr_return_counter, preparation_budget
          TO pls_web;
        GRANT INSERT ON TABLE inbox TO pls_web;

        GRANT SELECT ON TABLE {TABLES}, tr_return_counter, preparation_budget TO pls_worker;
        GRANT INSERT ON TABLE {TABLES} TO pls_worker;
        GRANT UPDATE ON TABLE
          case_record, dossier, dossier_revision, area_record, outbox, gate_attempt,
          gate_review_session, coverage_cell, defect, decision_intent, authority_grant,
          evidence_retention_policy, timer, preparation_interval, agent_run, closure
          TO pls_worker;

        GRANT SELECT ON TABLE timer, case_record TO pls_scheduler;
        GRANT UPDATE (status, last_claim_at, claim_lease) ON timer TO pls_scheduler;
        GRANT INSERT ON TABLE event TO pls_scheduler;

        -- TB-28 owns retention deletion.  TB-04 intentionally grants pls_retention
        -- no DELETE privilege and no executable deletion procedure.

        ALTER TABLE case_record OWNER TO pls_migrator;
        ALTER TABLE experiment_anchor OWNER TO pls_migrator;
        ALTER TABLE active_experiment_slot OWNER TO pls_migrator;
        ALTER TABLE pre_experiment_dismissal OWNER TO pls_migrator;
        ALTER TABLE dossier OWNER TO pls_migrator;
        ALTER TABLE dossier_revision OWNER TO pls_migrator;
        ALTER TABLE area_record OWNER TO pls_migrator;
        ALTER TABLE carry_forward OWNER TO pls_migrator;
        ALTER TABLE event OWNER TO pls_migrator;
        ALTER TABLE state_transition OWNER TO pls_migrator;
        ALTER TABLE inbox OWNER TO pls_migrator;
        ALTER TABLE outbox OWNER TO pls_migrator;
        ALTER TABLE gate_attempt OWNER TO pls_migrator;
        ALTER TABLE gate_review_session OWNER TO pls_migrator;
        ALTER TABLE coverage_cell OWNER TO pls_migrator;
        ALTER TABLE finding OWNER TO pls_migrator;
        ALTER TABLE gate_record OWNER TO pls_migrator;
        ALTER TABLE defect OWNER TO pls_migrator;
        ALTER TABLE decision_intent OWNER TO pls_migrator;
        ALTER TABLE consent OWNER TO pls_migrator;
        ALTER TABLE authority_grant OWNER TO pls_migrator;
        ALTER TABLE expense OWNER TO pls_migrator;
        ALTER TABLE external_action OWNER TO pls_migrator;
        ALTER TABLE workload_ledger OWNER TO pls_migrator;
        ALTER TABLE fact_record OWNER TO pls_migrator;
        ALTER TABLE evidence OWNER TO pls_migrator;
        ALTER TABLE artifact OWNER TO pls_migrator;
        ALTER TABLE late_evidence OWNER TO pls_migrator;
        ALTER TABLE linked_case OWNER TO pls_migrator;
        ALTER TABLE evidence_retention_policy OWNER TO pls_migrator;
        ALTER TABLE timer OWNER TO pls_migrator;
        ALTER TABLE preparation_interval OWNER TO pls_migrator;
        ALTER TABLE time_grant OWNER TO pls_migrator;
        ALTER TABLE context_package OWNER TO pls_migrator;
        ALTER TABLE agent_run OWNER TO pls_migrator;
        ALTER TABLE model_call OWNER TO pls_migrator;
        ALTER TABLE cost_record OWNER TO pls_migrator;
        ALTER TABLE price_catalog OWNER TO pls_migrator;
        ALTER TABLE data_policy_registry OWNER TO pls_migrator;
        ALTER TABLE cost_envelope OWNER TO pls_migrator;
        ALTER TABLE closure OWNER TO pls_migrator;
        ALTER TABLE decision_update OWNER TO pls_migrator;
        ALTER TABLE condition_record OWNER TO pls_migrator;
        ALTER TABLE review_stop_record OWNER TO pls_migrator;
        ALTER TABLE cycle_review_record OWNER TO pls_migrator;
        ALTER VIEW tr_return_counter OWNER TO pls_migrator;
        ALTER VIEW preparation_budget OWNER TO pls_migrator;
        ALTER FUNCTION pls_is_uuid_v7(uuid) OWNER TO pls_migrator;
        ALTER FUNCTION pls_reject_mutation() OWNER TO pls_migrator;
        ALTER FUNCTION pls_only_columns_change() OWNER TO pls_migrator;
        ALTER FUNCTION pls_case_update_guard() OWNER TO pls_migrator;
        ALTER FUNCTION pls_dossier_revision_guard() OWNER TO pls_migrator;
        ALTER FUNCTION pls_decision_intent_guard() OWNER TO pls_migrator;
        ALTER FUNCTION pls_closure_guard() OWNER TO pls_migrator;

        ALTER DEFAULT PRIVILEGES FOR ROLE pls_migrator IN SCHEMA public
          REVOKE ALL ON TABLES FROM PUBLIC;
        ALTER DEFAULT PRIVILEGES FOR ROLE pls_migrator IN SCHEMA public
          REVOKE ALL ON FUNCTIONS FROM PUBLIC;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
