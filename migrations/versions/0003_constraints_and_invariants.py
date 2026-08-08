"""Add relational constraints, enforced invariants, and recovery views."""

from alembic import op

revision = "0003_invariants"
down_revision = "0002_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        ALTER TABLE experiment_anchor
          ADD CONSTRAINT fk_experiment_anchor_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE active_experiment_slot
          ADD CONSTRAINT fk_active_slot_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE dossier
          ADD CONSTRAINT fk_dossier_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE dossier_revision
          ADD CONSTRAINT fk_revision_dossier FOREIGN KEY (dossier_id) REFERENCES dossier(id),
          ADD CONSTRAINT fk_revision_parent FOREIGN KEY (parent_revision_id) REFERENCES dossier_revision(id);
        ALTER TABLE area_record
          ADD CONSTRAINT fk_area_dossier FOREIGN KEY (dossier_id) REFERENCES dossier(id);
        ALTER TABLE event
          ADD CONSTRAINT fk_event_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_event_causation FOREIGN KEY (causation_id) REFERENCES event(id);
        ALTER TABLE state_transition
          ADD CONSTRAINT fk_transition_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_transition_event FOREIGN KEY (event_id) REFERENCES event(id);
        ALTER TABLE outbox
          ADD CONSTRAINT fk_outbox_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_outbox_event FOREIGN KEY (created_tx_event_id) REFERENCES event(id);
        ALTER TABLE gate_attempt
          ADD CONSTRAINT fk_gate_attempt_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_gate_attempt_revision_hash
            FOREIGN KEY (revision_id, content_hash) REFERENCES dossier_revision(id, content_hash);
        ALTER TABLE gate_review_session
          ADD CONSTRAINT fk_gate_session_attempt FOREIGN KEY (gate_attempt_id) REFERENCES gate_attempt(id);
        ALTER TABLE coverage_cell
          ADD CONSTRAINT fk_coverage_session FOREIGN KEY (session_id) REFERENCES gate_review_session(id);
        ALTER TABLE finding
          ADD CONSTRAINT fk_finding_session FOREIGN KEY (session_id) REFERENCES gate_review_session(id),
          ADD CONSTRAINT fk_finding_superseded FOREIGN KEY (superseded_by_finding_id) REFERENCES finding(id);
        ALTER TABLE gate_record
          ADD CONSTRAINT fk_gate_record_attempt FOREIGN KEY (gate_attempt_id) REFERENCES gate_attempt(id),
          ADD CONSTRAINT fk_gate_record_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_gate_record_revision_hash
            FOREIGN KEY (revision_id, content_hash) REFERENCES dossier_revision(id, content_hash);
        ALTER TABLE defect
          ADD CONSTRAINT fk_defect_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_defect_gate_record FOREIGN KEY (source_gate_record_id) REFERENCES gate_record(id);
        ALTER TABLE decision_intent
          ADD CONSTRAINT fk_intent_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_intent_revision_hash
            FOREIGN KEY (revision_id, content_hash) REFERENCES dossier_revision(id, content_hash);
        ALTER TABLE consent
          ADD CONSTRAINT fk_consent_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_consent_intent FOREIGN KEY (decision_intent_id) REFERENCES decision_intent(id),
          ADD CONSTRAINT fk_consent_revision_hash
            FOREIGN KEY (revision_id, content_hash) REFERENCES dossier_revision(id, content_hash),
          ADD CONSTRAINT fk_consent_revocation FOREIGN KEY (revoked_by_consent_id) REFERENCES consent(id);
        ALTER TABLE authority_grant
          ADD CONSTRAINT fk_grant_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_grant_consent FOREIGN KEY (consent_id) REFERENCES consent(id);
        ALTER TABLE expense
          ADD CONSTRAINT fk_expense_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_expense_grant_consent
            FOREIGN KEY (authorization_grant_id, consent_id)
            REFERENCES authority_grant(id, consent_id);
        ALTER TABLE external_action
          ADD CONSTRAINT fk_action_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_action_grant FOREIGN KEY (authority_grant_id) REFERENCES authority_grant(id);
        ALTER TABLE workload_ledger
          ADD CONSTRAINT fk_workload_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE fact_record
          ADD CONSTRAINT fk_fact_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_fact_snapshot FOREIGN KEY (snapshot_object_id) REFERENCES artifact(id),
          ADD CONSTRAINT fk_fact_superseded FOREIGN KEY (superseded_by) REFERENCES fact_record(id);
        ALTER TABLE evidence
          ADD CONSTRAINT fk_evidence_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_evidence_object FOREIGN KEY (object_id) REFERENCES artifact(id);
        ALTER TABLE late_evidence
          ADD CONSTRAINT fk_late_case FOREIGN KEY (terminal_case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_late_evidence FOREIGN KEY (evidence_id) REFERENCES evidence(id);
        ALTER TABLE linked_case
          ADD CONSTRAINT fk_linked_old_case FOREIGN KEY (old_case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_linked_new_case FOREIGN KEY (new_case_id) REFERENCES case_record(id);
        ALTER TABLE evidence_retention_policy
          ADD CONSTRAINT fk_retention_policy_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE timer
          ADD CONSTRAINT fk_timer_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE preparation_interval
          ADD CONSTRAINT fk_preparation_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE time_grant
          ADD CONSTRAINT fk_time_grant_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_time_grant_consent FOREIGN KEY (consent_id) REFERENCES consent(id);
        ALTER TABLE context_package
          ADD CONSTRAINT fk_context_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE agent_run
          ADD CONSTRAINT fk_run_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_run_context FOREIGN KEY (context_package_id) REFERENCES context_package(id),
          ADD CONSTRAINT fk_run_revision FOREIGN KEY (input_revision_id) REFERENCES dossier_revision(id),
          ADD CONSTRAINT fk_run_parent FOREIGN KEY (parent_run_id) REFERENCES agent_run(id),
          ADD CONSTRAINT fk_run_artifact FOREIGN KEY (result_artifact_id) REFERENCES artifact(id);
        ALTER TABLE dossier_revision
          ADD CONSTRAINT fk_revision_creator FOREIGN KEY (created_by_run_id) REFERENCES agent_run(id);
        ALTER TABLE model_call
          ADD CONSTRAINT fk_model_call_run FOREIGN KEY (agent_run_id) REFERENCES agent_run(id),
          ADD CONSTRAINT fk_model_call_session FOREIGN KEY (session_id) REFERENCES gate_review_session(id),
          ADD CONSTRAINT fk_model_call_cost FOREIGN KEY (cost_record_id) REFERENCES cost_record(id);
        ALTER TABLE closure
          ADD CONSTRAINT fk_closure_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE decision_update
          ADD CONSTRAINT fk_decision_update_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE condition_record
          ADD CONSTRAINT fk_condition_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_condition_revision FOREIGN KEY (fixed_in_revision_id) REFERENCES dossier_revision(id),
          ADD CONSTRAINT fk_condition_superseded FOREIGN KEY (superseded_by) REFERENCES condition_record(id);
        ALTER TABLE review_stop_record
          ADD CONSTRAINT fk_review_stop_case FOREIGN KEY (case_id) REFERENCES case_record(id),
          ADD CONSTRAINT fk_review_stop_condition FOREIGN KEY (trigger_condition_id) REFERENCES condition_record(id),
          ADD CONSTRAINT fk_review_stop_timer FOREIGN KEY (trigger_timer_id) REFERENCES timer(id),
          ADD CONSTRAINT fk_review_stop_event FOREIGN KEY (trigger_user_event_id) REFERENCES event(id),
          ADD CONSTRAINT fk_review_stop_revision FOREIGN KEY (revision_id) REFERENCES dossier_revision(id);
        ALTER TABLE cycle_review_record
          ADD CONSTRAINT fk_cycle_review_case FOREIGN KEY (case_id) REFERENCES case_record(id);
        ALTER TABLE carry_forward
          ADD CONSTRAINT fk_carry_source_record FOREIGN KEY (source_gate_record_id) REFERENCES gate_record(id),
          ADD CONSTRAINT fk_carry_source_revision FOREIGN KEY (source_revision_id) REFERENCES dossier_revision(id),
          ADD CONSTRAINT fk_carry_target_revision FOREIGN KEY (target_revision_id) REFERENCES dossier_revision(id);
        ALTER TABLE case_record
          ADD CONSTRAINT fk_case_revision FOREIGN KEY (current_revision_id) REFERENCES dossier_revision(id),
          ADD CONSTRAINT fk_case_reason_event FOREIGN KEY (reason_event_id) REFERENCES event(id),
          ADD CONSTRAINT ck_case_status_values CHECK (
            current_status IS NULL OR current_status IN (
              'CLOSED_COUNTED','CLOSED_NOT_COUNTED','PAUSED_USER','PAUSED_EXTERNAL','REJECTED_BEFORE_EXECUTION'
            )
          ),
          ADD CONSTRAINT ck_case_status_matches_state CHECK (
            current_status IS NULL OR current_status = current_state
          ),
          ADD CONSTRAINT ck_case_terminal_lock CHECK (
            (current_status IN ('CLOSED_COUNTED','CLOSED_NOT_COUNTED','REJECTED_BEFORE_EXECUTION')
              AND terminal_locked_at IS NOT NULL)
            OR
            ((current_status IS NULL OR current_status IN ('PAUSED_USER','PAUSED_EXTERNAL'))
              AND terminal_locked_at IS NULL)
          );

        CREATE UNIQUE INDEX uq_gate_attempt_open
          ON gate_attempt (case_id, gate_type, revision_id)
          WHERE status IN ('open','blocked_coverage_or_budget');

        CREATE UNIQUE INDEX uq_model_call_applied_per_attempt
          ON model_call (agent_run_id)
          WHERE applied = true;

        CREATE OR REPLACE FUNCTION pls_only_columns_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        DECLARE
          old_fixed jsonb := to_jsonb(OLD);
          new_fixed jsonb := to_jsonb(NEW);
          allowed text;
        BEGIN
          FOREACH allowed IN ARRAY TG_ARGV LOOP
            old_fixed := old_fixed - allowed;
            new_fixed := new_fixed - allowed;
          END LOOP;
          IF old_fixed IS DISTINCT FROM new_fixed THEN
            RAISE EXCEPTION '% immutable columns cannot be changed', TG_TABLE_NAME
              USING ERRCODE = '55000';
          END IF;
          RETURN NEW;
        END
        $function$;

        CREATE OR REPLACE FUNCTION pls_case_update_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          IF OLD.terminal_locked_at IS NOT NULL THEN
            IF (to_jsonb(OLD) - 'diagnostic_hold' - 'reason_event_id')
               IS DISTINCT FROM
               (to_jsonb(NEW) - 'diagnostic_hold' - 'reason_event_id') THEN
              RAISE EXCEPTION 'terminal case is locked' USING ERRCODE = '55000';
            END IF;
          ELSIF NEW.case_version <= OLD.case_version THEN
            RAISE EXCEPTION 'case_version must strictly increase on update' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END
        $function$;

        CREATE OR REPLACE FUNCTION pls_dossier_revision_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          IF OLD.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'published dossier revision is immutable' USING ERRCODE = '55000';
          END IF;
          IF NEW.id <> OLD.id OR NEW.dossier_id <> OLD.dossier_id
             OR NEW.revision_number <> OLD.revision_number THEN
            RAISE EXCEPTION 'dossier revision identity is immutable' USING ERRCODE = '55000';
          END IF;
          RETURN NEW;
        END
        $function$;

        CREATE OR REPLACE FUNCTION pls_decision_intent_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          IF (to_jsonb(OLD) - 'status' - 'consumed_at' - 'outcome_ref')
             IS DISTINCT FROM
             (to_jsonb(NEW) - 'status' - 'consumed_at' - 'outcome_ref') THEN
            RAISE EXCEPTION 'decision intent immutable fields cannot change' USING ERRCODE = '55000';
          END IF;
          IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'resolved decision intent cannot transition again' USING ERRCODE = '55000';
          END IF;
          IF NEW.status NOT IN ('consumed','expired','superseded') THEN
            RAISE EXCEPTION 'invalid decision intent transition' USING ERRCODE = '23514';
          END IF;
          IF NEW.status = 'consumed' AND NEW.consumed_at IS NULL THEN
            RAISE EXCEPTION 'consumed intent requires consumed_at' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END
        $function$;

        CREATE TRIGGER trg_case_update_guard
          BEFORE UPDATE ON case_record FOR EACH ROW EXECUTE FUNCTION pls_case_update_guard();
        CREATE TRIGGER trg_experiment_anchor_immutable
          BEFORE UPDATE OR DELETE ON experiment_anchor FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_dossier_revision_guard
          BEFORE UPDATE ON dossier_revision FOR EACH ROW EXECUTE FUNCTION pls_dossier_revision_guard();
        CREATE TRIGGER trg_decision_intent_guard
          BEFORE UPDATE ON decision_intent FOR EACH ROW EXECUTE FUNCTION pls_decision_intent_guard();

        CREATE TRIGGER trg_outbox_update
          BEFORE UPDATE ON outbox FOR EACH ROW
          EXECUTE FUNCTION pls_only_columns_change('status','attempts','delivered_at','telegram_message_id');
        CREATE TRIGGER trg_gate_attempt_update
          BEFORE UPDATE ON gate_attempt FOR EACH ROW EXECUTE FUNCTION pls_only_columns_change('status');
        CREATE TRIGGER trg_gate_session_update
          BEFORE UPDATE ON gate_review_session FOR EACH ROW EXECUTE FUNCTION pls_only_columns_change('status');
        CREATE TRIGGER trg_coverage_cell_update
          BEFORE UPDATE ON coverage_cell FOR EACH ROW
          EXECUTE FUNCTION pls_only_columns_change('outcome','finding_ids','validation_status');
        CREATE TRIGGER trg_defect_update
          BEFORE UPDATE ON defect FOR EACH ROW EXECUTE FUNCTION pls_only_columns_change('status_current');
        CREATE TRIGGER trg_authority_grant_update
          BEFORE UPDATE ON authority_grant FOR EACH ROW EXECUTE FUNCTION pls_only_columns_change('status');
        CREATE TRIGGER trg_timer_update
          BEFORE UPDATE ON timer FOR EACH ROW
          EXECUTE FUNCTION pls_only_columns_change('status','last_claim_at','claim_lease');
        CREATE TRIGGER trg_preparation_interval_update
          BEFORE UPDATE ON preparation_interval FOR EACH ROW EXECUTE FUNCTION pls_only_columns_change('ended_at');
        CREATE TRIGGER trg_agent_run_update
          BEFORE UPDATE ON agent_run FOR EACH ROW
          EXECUTE FUNCTION pls_only_columns_change('status','result_artifact_id','validation_result');

        CREATE TRIGGER trg_pre_experiment_dismissal_append_only BEFORE UPDATE OR DELETE ON pre_experiment_dismissal FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_carry_forward_append_only BEFORE UPDATE OR DELETE ON carry_forward FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_event_append_only BEFORE UPDATE OR DELETE ON event FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_state_transition_append_only BEFORE UPDATE OR DELETE ON state_transition FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_inbox_append_only BEFORE UPDATE OR DELETE ON inbox FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_finding_append_only BEFORE UPDATE OR DELETE ON finding FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_gate_record_append_only BEFORE UPDATE OR DELETE ON gate_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_consent_append_only BEFORE UPDATE OR DELETE ON consent FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_expense_append_only BEFORE UPDATE OR DELETE ON expense FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_external_action_append_only BEFORE UPDATE OR DELETE ON external_action FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_workload_append_only BEFORE UPDATE OR DELETE ON workload_ledger FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_fact_append_only BEFORE UPDATE OR DELETE ON fact_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_evidence_append_only BEFORE UPDATE OR DELETE ON evidence FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_artifact_append_only BEFORE UPDATE OR DELETE ON artifact FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_late_evidence_append_only BEFORE UPDATE OR DELETE ON late_evidence FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_linked_case_append_only BEFORE UPDATE OR DELETE ON linked_case FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_time_grant_append_only BEFORE UPDATE OR DELETE ON time_grant FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_context_package_append_only BEFORE UPDATE OR DELETE ON context_package FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_model_call_append_only BEFORE UPDATE OR DELETE ON model_call FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_cost_record_append_only BEFORE UPDATE OR DELETE ON cost_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_price_catalog_append_only BEFORE UPDATE OR DELETE ON price_catalog FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_data_policy_append_only BEFORE UPDATE OR DELETE ON data_policy_registry FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_cost_envelope_append_only BEFORE UPDATE OR DELETE ON cost_envelope FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_condition_append_only BEFORE UPDATE OR DELETE ON condition_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_review_stop_append_only BEFORE UPDATE OR DELETE ON review_stop_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_cycle_review_append_only BEFORE UPDATE OR DELETE ON cycle_review_record FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();
        CREATE TRIGGER trg_decision_update_append_only BEFORE UPDATE OR DELETE ON decision_update FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();

        CREATE OR REPLACE FUNCTION pls_closure_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          IF OLD.completed_at IS NOT NULL THEN
            RAISE EXCEPTION 'completed closure is immutable' USING ERRCODE = '55000';
          END IF;
          RETURN NEW;
        END
        $function$;
        CREATE TRIGGER trg_closure_guard
          BEFORE UPDATE ON closure FOR EACH ROW EXECUTE FUNCTION pls_closure_guard();
        CREATE TRIGGER trg_closure_no_delete
          BEFORE DELETE ON closure FOR EACH ROW EXECUTE FUNCTION pls_reject_mutation();

        CREATE VIEW tr_return_counter AS
          SELECT case_id, count(*)::bigint AS count
          FROM gate_record
          WHERE result = 'TECH_REVIEW_RETURNED'
          GROUP BY case_id;

        CREATE VIEW preparation_budget AS
          WITH merged AS (
            SELECT case_id,
                   range_agg(tstzrange(started_at, COALESCE(ended_at, now()), '[)')) AS spans
            FROM preparation_interval
            GROUP BY case_id
          ), expanded AS (
            SELECT case_id, unnest(spans) AS span
            FROM merged
          )
          SELECT case_id,
                 sum(extract(epoch FROM (upper(span) - lower(span))) / 60.0) AS consumed_minutes
          FROM expanded
          GROUP BY case_id;
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
