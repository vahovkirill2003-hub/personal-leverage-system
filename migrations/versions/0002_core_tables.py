"""Create the 45 persistence entities from data-model specification section 3."""

from alembic import op

revision = "0002_core_tables"
down_revision = "0001_roles_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE case_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          created_at timestamptz NOT NULL DEFAULT now(),
          current_state text NOT NULL,
          current_status text,
          case_version bigint NOT NULL DEFAULT 0 CHECK (case_version >= 0),
          current_revision_id uuid,
          depth_level text NOT NULL CHECK (depth_level IN ('min','std','elevated')),
          timezone text NOT NULL,
          terminal_locked_at timestamptz,
          diagnostic_hold boolean NOT NULL DEFAULT false,
          reason_event_id uuid
        );

        CREATE TABLE experiment_anchor (
          case_id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(case_id)),
          experiment_started_at timestamptz NOT NULL,
          accepted_duration_days smallint NOT NULL CHECK (accepted_duration_days BETWEEN 3 AND 14),
          planned_deadline_at timestamptz NOT NULL,
          absolute_deadline_at timestamptz NOT NULL,
          CHECK (absolute_deadline_at <= experiment_started_at + interval '14 days')
        );

        CREATE TABLE active_experiment_slot (
          user_scope text PRIMARY KEY CHECK (user_scope = 'single-user'),
          case_id uuid NOT NULL UNIQUE CHECK (pls_is_uuid_v7(case_id))
        );

        CREATE TABLE pre_experiment_dismissal (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          original_request_ref text NOT NULL,
          dismissed_at timestamptz NOT NULL,
          stage text NOT NULL CHECK (stage IN ('INTAKE','CLARIFICATION','FACT_UNKNOWN_MAPPING')),
          reason text NOT NULL,
          applied_rule text NOT NULL,
          actual_system_time_sec numeric NOT NULL CHECK (actual_system_time_sec >= 0),
          user_confirmation_event_id uuid,
          no_external_action boolean NOT NULL DEFAULT true CHECK (no_external_action),
          no_expense boolean NOT NULL DEFAULT true CHECK (no_expense),
          no_obligation boolean NOT NULL DEFAULT true CHECK (no_obligation),
          disposition text NOT NULL
        );

        CREATE TABLE dossier (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL UNIQUE CHECK (pls_is_uuid_v7(case_id))
        );

        CREATE TABLE dossier_revision (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          dossier_id uuid NOT NULL CHECK (pls_is_uuid_v7(dossier_id)),
          revision_number integer NOT NULL CHECK (revision_number > 0),
          parent_revision_id uuid,
          content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
          materiality text NOT NULL CHECK (materiality IN ('material','non_material','undetermined')),
          delta_ref text,
          created_by_run_id uuid,
          published_at timestamptz,
          UNIQUE (dossier_id, revision_number),
          UNIQUE (dossier_id, content_hash),
          UNIQUE (id, content_hash)
        );

        CREATE TABLE area_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          dossier_id uuid NOT NULL CHECK (pls_is_uuid_v7(dossier_id)),
          area_id smallint NOT NULL CHECK (area_id BETWEEN 1 AND 27),
          canonical_record_ref text NOT NULL,
          not_applicable boolean NOT NULL DEFAULT false,
          normative_basis text,
          CHECK (NOT not_applicable OR normative_basis IS NOT NULL),
          UNIQUE (dossier_id, area_id)
        );

        CREATE TABLE carry_forward (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          gate_type text NOT NULL CHECK (gate_type IN ('TR','SA','UA')),
          source_gate_record_id uuid NOT NULL,
          source_revision_id uuid NOT NULL,
          target_revision_id uuid NOT NULL,
          full_delta_ref text NOT NULL,
          materiality_evidence_ref text NOT NULL,
          scope jsonb NOT NULL,
          exclusions jsonb NOT NULL,
          owner_actor text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE event (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid,
          type text NOT NULL,
          actor_type text NOT NULL CHECK (actor_type IN ('user','system','agent_run','timer','admin')),
          actor_id text,
          occurred_at timestamptz NOT NULL,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          causation_id uuid,
          correlation_id uuid,
          payload_ref text
        );

        CREATE TABLE state_transition (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          event_id uuid NOT NULL,
          from_state text NOT NULL,
          to_state text NOT NULL,
          guard_results_ref text NOT NULL,
          case_version_before bigint NOT NULL CHECK (case_version_before >= 0),
          case_version_after bigint NOT NULL CHECK (case_version_after > case_version_before),
          UNIQUE (case_id, case_version_after)
        );

        CREATE TABLE inbox (
          bot_id text NOT NULL,
          update_id bigint NOT NULL,
          received_at timestamptz NOT NULL DEFAULT now(),
          processing_result_ref text,
          PRIMARY KEY (bot_id, update_id)
        );

        CREATE TABLE outbox (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          logical_notification_id text NOT NULL UNIQUE,
          case_id uuid,
          kind text NOT NULL CHECK (kind IN ('informational','decision')),
          payload_ref text NOT NULL,
          created_tx_event_id uuid NOT NULL,
          status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','delivering','delivered','terminal_error')),
          attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
          delivered_at timestamptz,
          telegram_message_id text
        );

        CREATE TABLE gate_attempt (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          gate_type text NOT NULL CHECK (gate_type IN ('TR','SA','UA')),
          mode text NOT NULL CHECK (mode IN ('INITIAL','REVALIDATED','RESUMPTION_ONLY')),
          revision_id uuid NOT NULL,
          content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
          criteria_version text NOT NULL,
          status text NOT NULL DEFAULT 'open'
            CHECK (status IN ('open','blocked_coverage_or_budget','completed'))
        );

        CREATE TABLE gate_review_session (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          gate_attempt_id uuid NOT NULL UNIQUE,
          role text NOT NULL,
          purpose text NOT NULL DEFAULT 'verification' CHECK (purpose = 'verification'),
          policy_versions jsonb NOT NULL,
          call_count_limit integer NOT NULL CHECK (call_count_limit > 0),
          cost_limit numeric NOT NULL CHECK (cost_limit >= 0),
          status text NOT NULL
        );

        CREATE TABLE coverage_cell (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          session_id uuid NOT NULL,
          element_kind text NOT NULL CHECK (element_kind IN ('area','edge')),
          element_id text NOT NULL,
          assigned_pass text NOT NULL,
          input_hashes jsonb NOT NULL,
          criterion text NOT NULL,
          outcome text CHECK (outcome IN ('CHECKED_OK','FINDING','NOT_APPLICABLE','INCONCLUSIVE')),
          finding_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          validation_status text NOT NULL,
          UNIQUE (session_id, element_kind, element_id)
        );

        CREATE TABLE finding (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          session_id uuid NOT NULL,
          pass_call_id uuid,
          class text NOT NULL,
          severity text NOT NULL,
          affected_refs jsonb NOT NULL,
          criterion text NOT NULL,
          counterexample text,
          created_at timestamptz NOT NULL DEFAULT now(),
          superseded_by_finding_id uuid
        );

        CREATE TABLE gate_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          gate_attempt_id uuid NOT NULL UNIQUE,
          gate_type text NOT NULL CHECK (gate_type IN ('TR','SA','UA')),
          mode text NOT NULL CHECK (mode IN ('INITIAL','REVALIDATED','RESUMPTION_ONLY')),
          case_id uuid NOT NULL,
          revision_id uuid NOT NULL,
          content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
          result text NOT NULL,
          actor_run_id uuid,
          user_decision_intent_id uuid,
          criteria_version text NOT NULL,
          context_package_hash text,
          defect_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          gap_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (
            (gate_type = 'TR' AND result IN ('TECH_REVIEW_PASSED','TECH_REVIEW_RETURNED')) OR
            (gate_type = 'SA' AND result IN ('ACCEPTED','ACCEPTED_WITH_DISCLOSED_GAPS','RETURNED')) OR
            (gate_type = 'UA' AND result IN ('USER_ACCEPTED','USER_RETURNED','USER_DEFERRED','USER_REJECTED'))
          )
        );

        CREATE TABLE defect (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          source_gate_record_id uuid NOT NULL,
          class text NOT NULL,
          criterion text NOT NULL,
          affected_refs jsonb NOT NULL,
          status_current text NOT NULL
        );

        CREATE TABLE decision_intent (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
          idempotency_key text NOT NULL UNIQUE,
          case_id uuid NOT NULL,
          revision_id uuid,
          content_hash text,
          kind text NOT NULL CHECK (kind IN ('UA','action','expense','gap','extra_time','review_stop','closure_obligation','decision_update','linked_case')),
          subject_refs jsonb NOT NULL,
          amount numeric,
          currency text,
          purpose text,
          shown_risks_ref text NOT NULL,
          allowed_responses jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          nonce text NOT NULL,
          status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','consumed','expired','superseded')),
          consumed_at timestamptz,
          outcome_ref text,
          CHECK (kind <> 'expense' OR (amount IS NOT NULL AND currency IS NOT NULL AND purpose IS NOT NULL))
        );

        CREATE TABLE consent (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          decision_intent_id uuid NOT NULL UNIQUE,
          revision_id uuid NOT NULL,
          content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
          subject text NOT NULL,
          shown_risks_ref text NOT NULL,
          decided_at timestamptz NOT NULL,
          revoked_by_consent_id uuid
        );

        CREATE TABLE authority_grant (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          consent_id uuid NOT NULL,
          scope_action_ref text,
          scope_data jsonb NOT NULL,
          scope_addressee text,
          scope_amount numeric,
          scope_currency text,
          scope_purpose text,
          valid_until timestamptz,
          status text NOT NULL CHECK (status IN ('active','consumed','revoked','inapplicable')),
          UNIQUE (id, consent_id)
        );

        CREATE TABLE expense (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          request_amount numeric NOT NULL CHECK (request_amount >= 0),
          request_currency text NOT NULL,
          request_purpose text NOT NULL,
          request_action_ref text NOT NULL,
          request_risk text NOT NULL,
          request_term text NOT NULL,
          authorization_grant_id uuid NOT NULL,
          consent_id uuid NOT NULL UNIQUE,
          actual_fact_ref text
        );

        CREATE TABLE external_action (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          contract_ref text NOT NULL,
          authority_grant_id uuid NOT NULL,
          planned_version integer NOT NULL CHECK (planned_version > 0),
          executed_at timestamptz,
          executed_by text NOT NULL DEFAULT 'Кирилл' CHECK (executed_by = 'Кирилл'),
          evidence_links jsonb NOT NULL DEFAULT '[]'::jsonb
        );

        CREATE TABLE workload_ledger (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          week_key text NOT NULL
            CHECK (week_key ~ '^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$'),
          reported_minutes integer NOT NULL CHECK (reported_minutes >= 0),
          source_ref text NOT NULL
        );

        CREATE TABLE fact_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          kind text NOT NULL CHECK (kind IN ('fact','assumption','unknown','recommendation')),
          statement_ref text NOT NULL,
          source text NOT NULL,
          retrieved_at timestamptz,
          snapshot_object_id uuid,
          freshness text,
          confidence text NOT NULL CHECK (confidence IN ('высокая','средняя','низкая','не оценена')),
          superseded_by uuid
        );

        CREATE TABLE evidence (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          provenance text NOT NULL,
          source text NOT NULL,
          captured_at timestamptz NOT NULL,
          object_id uuid,
          content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
          strength text NOT NULL CHECK (strength IN ('сильное','умеренное','слабое','недостаточное')),
          rationale text NOT NULL,
          attestation_ref text,
          links jsonb NOT NULL DEFAULT '[]'::jsonb,
          CHECK (attestation_ref IS NULL OR strength IN ('умеренное','слабое','недостаточное'))
        );

        CREATE TABLE artifact (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          object_key text NOT NULL UNIQUE,
          sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
          size bigint NOT NULL CHECK (size >= 0),
          mime text NOT NULL,
          quarantine_status text NOT NULL,
          retention_class text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE late_evidence (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          terminal_case_id uuid NOT NULL,
          evidence_id uuid NOT NULL,
          received_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE linked_case (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          old_case_id uuid NOT NULL,
          new_case_id uuid NOT NULL,
          relation_type text NOT NULL,
          old_question_ref text NOT NULL,
          new_question_ref text NOT NULL,
          baseline_difference_ref text NOT NULL,
          CHECK (old_case_id <> new_case_id)
        );

        CREATE TABLE evidence_retention_policy (
          case_id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(case_id)),
          composition jsonb NOT NULL,
          form text NOT NULL,
          purpose text NOT NULL,
          trigger_spec jsonb NOT NULL
        );

        CREATE TABLE timer (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          kind text NOT NULL,
          due_at timestamptz NOT NULL,
          calendar_rule text,
          timezone text,
          status text NOT NULL CHECK (status IN ('armed','claimed','fired','cancelled')),
          last_claim_at timestamptz,
          claim_lease interval,
          firing_idempotency_key text NOT NULL UNIQUE
        );

        CREATE TABLE preparation_interval (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          started_at timestamptz NOT NULL,
          ended_at timestamptz,
          job_or_run_id uuid NOT NULL,
          stage_bucket text NOT NULL,
          lease_heartbeat_at timestamptz,
          CHECK (ended_at IS NULL OR ended_at >= started_at)
        );

        CREATE TABLE time_grant (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          granted_minutes integer NOT NULL CHECK (granted_minutes > 0),
          consent_id uuid NOT NULL
        );

        CREATE TABLE context_package (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          role text NOT NULL,
          case_id uuid NOT NULL,
          manifest jsonb NOT NULL,
          policy_version text NOT NULL,
          package_hash text NOT NULL CHECK (package_hash ~ '^[0-9a-f]{64}$'),
          classification text NOT NULL
        );

        CREATE TABLE agent_run (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          role text NOT NULL,
          purpose text NOT NULL CHECK (purpose IN ('production','verification')),
          attempt integer NOT NULL CHECK (attempt > 0),
          context_package_id uuid NOT NULL,
          input_revision_id uuid,
          allowed_tools jsonb NOT NULL,
          budget jsonb NOT NULL,
          deadline timestamptz NOT NULL,
          parent_run_id uuid,
          producer_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          status text NOT NULL,
          result_artifact_id uuid,
          validation_result jsonb,
          UNIQUE (case_id, role, attempt)
        );

        CREATE TABLE model_call (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          agent_run_id uuid NOT NULL,
          session_id uuid,
          pass text,
          provider_adapter text NOT NULL,
          model_alias text NOT NULL,
          returned_model_id text,
          contract_version text NOT NULL,
          context_package_hash text NOT NULL CHECK (context_package_hash ~ '^[0-9a-f]{64}$'),
          stateless boolean NOT NULL,
          provider_state_id_hash text CHECK (provider_state_id_hash IS NULL OR provider_state_id_hash ~ '^[0-9a-f]{64}$'),
          provider_state_reason text,
          provider_state_expiry timestamptz,
          data_policy_version text NOT NULL,
          data_policy_effective_date date NOT NULL,
          tool_permissions jsonb NOT NULL,
          tool_proposals_ref text,
          tool_executions_ref text,
          store_params jsonb NOT NULL,
          started_at timestamptz NOT NULL,
          ended_at timestamptz,
          stop_reason text,
          usage jsonb NOT NULL,
          cost_record_id uuid,
          response_hash text CHECK (response_hash IS NULL OR response_hash ~ '^[0-9a-f]{64}$'),
          validation_result jsonb,
          applied boolean NOT NULL DEFAULT false,
          CHECK (
            provider_state_id_hash IS NULL OR
            (provider_state_reason IS NOT NULL AND provider_state_expiry IS NOT NULL)
          )
        );

        CREATE TABLE cost_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          scope text NOT NULL CHECK (scope IN ('model_call','process','db','storage','backup','monitoring','network','test')),
          usage jsonb NOT NULL,
          provider_charge_estimate numeric,
          provider_charge_actual numeric,
          tariff_snapshot_date date NOT NULL,
          billing_period text NOT NULL
        );

        CREATE TABLE price_catalog (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          source text NOT NULL,
          effective_date date NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE data_policy_registry (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          source text NOT NULL,
          effective_date date NOT NULL,
          version text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (version, effective_date)
        );

        CREATE TABLE cost_envelope (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          source text NOT NULL,
          effective_date date NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE closure (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          actions_ref text NOT NULL,
          resources_ref text NOT NULL,
          evidence_ref text NOT NULL,
          obligations_ref text NOT NULL,
          stop_justification_ref text,
          preliminary_countability boolean NOT NULL,
          completed_at timestamptz
        );

        CREATE TABLE decision_update (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          before_after_ref text NOT NULL,
          explicit_user_decision jsonb NOT NULL,
          cycle_score_0_10 numeric NOT NULL CHECK (cycle_score_0_10 BETWEEN 0 AND 10),
          repeat_readiness text NOT NULL,
          user_time interval NOT NULL,
          deferred boolean NOT NULL DEFAULT false,
          deferred_parameters jsonb,
          accepted_at timestamptz NOT NULL,
          CHECK (NOT deferred OR deferred_parameters IS NOT NULL)
        );

        CREATE TABLE condition_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          kind text NOT NULL CHECK (kind IN ('success','review','stop')),
          statement_ref text NOT NULL,
          interpretation_rules_ref text NOT NULL,
          fixed_in_revision_id uuid NOT NULL,
          superseded_by uuid
        );

        CREATE TABLE review_stop_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          trigger_condition_id uuid,
          trigger_timer_id uuid,
          trigger_user_event_id uuid,
          outcome text NOT NULL,
          justification_ref text,
          waiting_ref text,
          revision_id uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (num_nonnulls(trigger_condition_id, trigger_timer_id, trigger_user_event_id) = 1)
        );

        CREATE TABLE cycle_review_record (
          id uuid PRIMARY KEY CHECK (pls_is_uuid_v7(id)),
          case_id uuid NOT NULL,
          trigger_basis text NOT NULL,
          history_ref text NOT NULL,
          root_cause text NOT NULL,
          new_vs_repeated_ref text NOT NULL,
          resolution_owner text NOT NULL,
          proposed_outcome text NOT NULL,
          user_decision_ref text
        );
        """
    )


def downgrade() -> None:
    raise RuntimeError("PLS database migrations are forward-only")
