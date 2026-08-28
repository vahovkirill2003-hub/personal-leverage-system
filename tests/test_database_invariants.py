from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("PLS_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="PLS_TEST_DATABASE_URL is required for PostgreSQL invariant tests",
)


def uid(number: int) -> str:
    """Return deterministic synthetic UUIDv7 values for DB fixtures."""
    return f"01980000-0000-7000-8000-{number:012x}"


@pytest.fixture(scope="module")
def db() -> psycopg.Connection:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        config = Config(ROOT / "alembic.ini")
        command.upgrade(config, "head")
        connection = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
        yield connection
        connection.close()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def rejects(db: psycopg.Connection, sql: str, params: tuple[object, ...] = ()) -> None:
    with pytest.raises(psycopg.Error):
        db.execute(sql, params)


def insert_case(db: psycopg.Connection, case_id: str, *, terminal: bool = False) -> None:
    if terminal:
        db.execute(
            """
            INSERT INTO case_record
              (id, current_state, current_status, case_version, depth_level, timezone, terminal_locked_at)
            VALUES (%s, 'CLOSED_COUNTED', 'CLOSED_COUNTED', 1, 'std', 'UTC', now())
            """,
            (case_id,),
        )
    else:
        db.execute(
            """
            INSERT INTO case_record (id, current_state, case_version, depth_level, timezone)
            VALUES (%s, 'EXECUTION', 0, 'std', 'UTC')
            """,
            (case_id,),
        )


def seed_revision(
    db: psycopg.Connection,
    case_id: str,
    dossier_id: str,
    revision_id: str,
    content_hash: str,
    *,
    published: bool = False,
) -> None:
    db.execute("INSERT INTO dossier (id, case_id) VALUES (%s, %s)", (dossier_id, case_id))
    db.execute(
        """
        INSERT INTO dossier_revision
          (id, dossier_id, revision_number, content_hash, materiality, published_at)
        VALUES (%s, %s, 1, %s, 'material', CASE WHEN %s THEN now() ELSE NULL END)
        """,
        (revision_id, dossier_id, content_hash, published),
    )


def test_t03_set_once_slot_terminal_lock_and_counter(db: psycopg.Connection) -> None:
    case_one, case_two, terminal_case, counter_case = (uid(1), uid(2), uid(3), uid(4))
    for case_id in (case_one, case_two, counter_case):
        insert_case(db, case_id)
    insert_case(db, terminal_case, terminal=True)

    db.execute(
        """
        INSERT INTO experiment_anchor
          (case_id, experiment_started_at, accepted_duration_days, planned_deadline_at, absolute_deadline_at)
        VALUES (%s, now(), 7, now() + interval '7 days', now() + interval '14 days')
        """,
        (case_one,),
    )
    rejects(
        db,
        "UPDATE experiment_anchor SET accepted_duration_days = 8 WHERE case_id = %s",
        (case_one,),
    )
    rejects(db, "DELETE FROM experiment_anchor WHERE case_id = %s", (case_one,))

    db.execute(
        "INSERT INTO active_experiment_slot (user_scope, case_id) VALUES ('single-user', %s)",
        (case_one,),
    )
    rejects(
        db,
        "INSERT INTO active_experiment_slot (user_scope, case_id) VALUES ('single-user', %s)",
        (case_two,),
    )

    rejects(
        db,
        "UPDATE case_record SET current_state = 'EXECUTION', case_version = 2 WHERE id = %s",
        (terminal_case,),
    )
    db.execute(
        "UPDATE case_record SET diagnostic_hold = true WHERE id = %s",
        (terminal_case,),
    )

    dossier_id, revision_id = uid(10), uid(11)
    content_hash = "a" * 64
    seed_revision(db, counter_case, dossier_id, revision_id, content_hash)
    for offset in (20, 21):
        attempt_id, record_id = uid(offset), uid(offset + 10)
        db.execute(
            """
            INSERT INTO gate_attempt
              (id, case_id, gate_type, mode, revision_id, content_hash, criteria_version, status)
            VALUES (%s, %s, 'TR', 'INITIAL', %s, %s, 'synthetic-v1', 'completed')
            """,
            (attempt_id, counter_case, revision_id, content_hash),
        )
        db.execute(
            """
            INSERT INTO gate_record
              (id, gate_attempt_id, gate_type, mode, case_id, revision_id, content_hash,
               result, criteria_version)
            VALUES (%s, %s, 'TR', 'INITIAL', %s, %s, %s,
                    'TECH_REVIEW_RETURNED', 'synthetic-v1')
            """,
            (record_id, attempt_id, counter_case, revision_id, content_hash),
        )

    assert db.execute(
        "SELECT count FROM tr_return_counter WHERE case_id = %s", (counter_case,)
    ).fetchone() == (2,)
    rejects(db, "DELETE FROM gate_record WHERE case_id = %s", (counter_case,))
    rejects(
        db,
        "UPDATE gate_record SET result = 'TECH_REVIEW_PASSED' WHERE case_id = %s",
        (counter_case,),
    )
    assert db.execute(
        "SELECT count FROM tr_return_counter WHERE case_id = %s", (counter_case,)
    ).fetchone() == (2,)


def test_tb04_supplemental_constraints(db: psycopg.Connection) -> None:
    case_id = uid(100)
    insert_case(db, case_id)

    event_id = uid(101)
    db.execute(
        """
        INSERT INTO event (id, case_id, type, actor_type, occurred_at)
        VALUES (%s, %s, 'SYNTHETIC', 'system', now())
        """,
        (event_id, case_id),
    )
    db.execute(
        """
        INSERT INTO outbox
          (id, logical_notification_id, case_id, kind, payload_ref, created_tx_event_id)
        VALUES (%s, 'synthetic-notification', %s, 'informational', 'synthetic-ref', %s)
        """,
        (uid(102), case_id, event_id),
    )
    rejects(
        db,
        """
        INSERT INTO outbox
          (id, logical_notification_id, case_id, kind, payload_ref, created_tx_event_id)
        VALUES (%s, 'synthetic-notification', %s, 'informational', 'synthetic-ref-2', %s)
        """,
        (uid(103), case_id, event_id),
    )

    rejects(
        db,
        """
        INSERT INTO evidence
          (id, case_id, provenance, source, captured_at, content_hash, strength, rationale, attestation_ref)
        VALUES (%s, %s, 'synthetic', 'synthetic', now(), %s, 'сильное', 'synthetic', 'self')
        """,
        (uid(104), case_id, "b" * 64),
    )
    db.execute(
        """
        INSERT INTO evidence
          (id, case_id, provenance, source, captured_at, content_hash, strength, rationale, attestation_ref)
        VALUES (%s, %s, 'synthetic', 'synthetic', now(), %s, 'умеренное', 'synthetic', 'self')
        """,
        (uid(105), case_id, "c" * 64),
    )

    rejects(
        db,
        "INSERT INTO workload_ledger (id, case_id, week_key, reported_minutes, source_ref) VALUES (%s, %s, '2026-54', 1, 'synthetic')",
        (uid(106), case_id),
    )
    db.execute(
        "INSERT INTO workload_ledger (id, case_id, week_key, reported_minutes, source_ref) VALUES (%s, %s, '2026-W32', 1, 'synthetic')",
        (uid(107), case_id),
    )

    context_id, run_id = uid(108), uid(109)
    db.execute(
        """
        INSERT INTO context_package (id, role, case_id, manifest, policy_version, package_hash, classification)
        VALUES (%s, 'synthetic', %s, '{}'::jsonb, 'synthetic-v1', %s, 'synthetic')
        """,
        (context_id, case_id, "d" * 64),
    )
    db.execute(
        """
        INSERT INTO agent_run
          (id, case_id, role, purpose, attempt, context_package_id, allowed_tools, budget, deadline, status)
        VALUES (%s, %s, 'synthetic', 'production', 1, %s, '[]'::jsonb, '{}'::jsonb,
                now() + interval '1 hour', 'running')
        """,
        (run_id, case_id, context_id),
    )
    call_sql = """
        INSERT INTO model_call
          (id, agent_run_id, provider_adapter, model_alias, contract_version, context_package_hash,
           stateless, data_policy_version, data_policy_effective_date, tool_permissions, store_params,
           started_at, usage, applied)
        VALUES (%s, %s, 'synthetic-provider', 'synthetic-model', 'v1', %s,
                true, 'synthetic-policy', DATE '2026-08-08', '[]'::jsonb, '{}'::jsonb,
                now(), '{}'::jsonb, true)
    """
    db.execute(call_sql, (uid(110), run_id, "d" * 64))
    rejects(db, call_sql, (uid(111), run_id, "d" * 64))


def test_t04_malicious_worker_is_rejected_by_postgresql(db: psycopg.Connection) -> None:
    case_id, terminal_case = uid(200), uid(201)
    insert_case(db, case_id)
    insert_case(db, terminal_case, terminal=True)
    dossier_id, revision_id = uid(202), uid(203)
    content_hash = "e" * 64
    seed_revision(db, case_id, dossier_id, revision_id, content_hash, published=True)

    intent_id, consent_id, grant_id, expense_id = uid(204), uid(205), uid(206), uid(207)
    db.execute(
        """
        INSERT INTO decision_intent
          (id, token_hash, idempotency_key, case_id, revision_id, content_hash, kind,
           subject_refs, amount, currency, purpose, shown_risks_ref, allowed_responses,
           expires_at, nonce)
        VALUES (%s, %s, 'synthetic-intent', %s, %s, %s, 'expense',
                '[]'::jsonb, 10, 'RUB', 'synthetic', 'synthetic-risks', '["yes","no"]'::jsonb,
                now() + interval '1 hour', 'synthetic-nonce')
        """,
        (intent_id, "f" * 64, case_id, revision_id, content_hash),
    )
    db.execute(
        """
        INSERT INTO consent
          (id, case_id, decision_intent_id, revision_id, content_hash, subject, shown_risks_ref, decided_at)
        VALUES (%s, %s, %s, %s, %s, 'synthetic', 'synthetic-risks', now())
        """,
        (consent_id, case_id, intent_id, revision_id, content_hash),
    )
    db.execute(
        """
        INSERT INTO authority_grant
          (id, case_id, consent_id, scope_action_ref, scope_data, scope_addressee,
           scope_amount, scope_currency, scope_purpose, status)
        VALUES (%s, %s, %s, 'synthetic-action', '{"kind":"synthetic"}'::jsonb,
                'synthetic-addressee', 10, 'RUB', 'synthetic', 'active')
        """,
        (grant_id, case_id, consent_id),
    )
    db.execute(
        """
        INSERT INTO expense
          (id, case_id, request_amount, request_currency, request_purpose, request_action_ref,
           request_risk, request_term, authorization_grant_id, consent_id)
        VALUES (%s, %s, 10, 'RUB', 'synthetic', 'synthetic-action', 'synthetic-risk',
                'synthetic-term', %s, %s)
        """,
        (expense_id, case_id, grant_id, consent_id),
    )

    context_id, run_id = uid(208), uid(209)
    db.execute(
        """
        INSERT INTO context_package (id, role, case_id, manifest, policy_version, package_hash, classification)
        VALUES (%s, 'synthetic', %s, '{}'::jsonb, 'synthetic-v1', %s, 'synthetic')
        """,
        (context_id, case_id, "1" * 64),
    )
    db.execute(
        """
        INSERT INTO agent_run
          (id, case_id, role, purpose, attempt, context_package_id, allowed_tools, budget, deadline, status)
        VALUES (%s, %s, 'synthetic', 'production', 1, %s, '[]'::jsonb, '{}'::jsonb,
                now() + interval '1 hour', 'running')
        """,
        (run_id, case_id, context_id),
    )

    event_id = uid(210)
    db.execute(
        "INSERT INTO event (id, case_id, type, actor_type, occurred_at) VALUES (%s, %s, 'SYNTHETIC', 'system', now())",
        (event_id, case_id),
    )
    db.execute(
        """
        INSERT INTO experiment_anchor
          (case_id, experiment_started_at, accepted_duration_days, planned_deadline_at, absolute_deadline_at)
        VALUES (%s, now(), 7, now() + interval '7 days', now() + interval '14 days')
        """,
        (case_id,),
    )
    attempt_id, record_id = uid(211), uid(212)
    db.execute(
        """
        INSERT INTO gate_attempt
          (id, case_id, gate_type, mode, revision_id, content_hash, criteria_version, status)
        VALUES (%s, %s, 'TR', 'INITIAL', %s, %s, 'synthetic-v1', 'completed')
        """,
        (attempt_id, case_id, revision_id, content_hash),
    )
    db.execute(
        """
        INSERT INTO gate_record
          (id, gate_attempt_id, gate_type, mode, case_id, revision_id, content_hash,
           result, criteria_version)
        VALUES (%s, %s, 'TR', 'INITIAL', %s, %s, %s, 'TECH_REVIEW_PASSED', 'synthetic-v1')
        """,
        (record_id, attempt_id, case_id, revision_id, content_hash),
    )

    db.execute("SET ROLE pls_worker")
    try:
        assert db.execute("SELECT current_user").fetchone() == ("pls_worker",)
        db.execute(
            """
            INSERT INTO workload_ledger (id, case_id, week_key, reported_minutes, source_ref)
            VALUES (%s, %s, '2026-W32', 1, 'synthetic-worker-positive-control')
            """,
            (uid(214), case_id),
        )
        # `14 v0.3` §5 п. 14 and §12: the worker is the only executor of
        # commands, so SELECT and INSERT on `command_receipt` must succeed for
        # it, while UPDATE and DELETE are refused by the database itself.
        receipt_id = uid(215)
        db.execute(
            """
            INSERT INTO command_receipt
              (id, command_type, idempotency_key, case_id, actor_type, outcome_ref, outcome_kind)
            VALUES (%s, 'SubmitOpportunity', 'synthetic-worker-receipt', %s, 'user',
                    'synthetic-outcome', 'applied')
            """,
            (receipt_id, case_id),
        )
        assert db.execute(
            "SELECT outcome_kind FROM command_receipt WHERE id = %s", (receipt_id,)
        ).fetchone() == ("applied",)

        attacks = (
            ("UPDATE event SET type = 'TAMPERED' WHERE id = %s", (event_id,)),
            ("UPDATE command_receipt SET outcome_kind = 'rejected' WHERE id = %s", (receipt_id,)),
            ("DELETE FROM command_receipt WHERE id = %s", (receipt_id,)),
            (
                """
                INSERT INTO command_receipt
                  (id, command_type, idempotency_key, case_id, actor_type, outcome_ref, outcome_kind)
                VALUES (%s, 'SubmitOpportunity', 'synthetic-worker-receipt', %s, 'user',
                        'synthetic-second-outcome', 'applied')
                """,
                (uid(216), case_id),
            ),
            ("DELETE FROM event WHERE id = %s", (event_id,)),
            (
                "UPDATE experiment_anchor SET accepted_duration_days = 8 WHERE case_id = %s",
                (case_id,),
            ),
            ("DELETE FROM experiment_anchor WHERE case_id = %s", (case_id,)),
            (
                """
                INSERT INTO gate_record
                  (id, gate_attempt_id, gate_type, mode, case_id, revision_id, content_hash,
                   result, criteria_version)
                VALUES (%s, %s, 'TR', 'INITIAL', %s, %s, %s,
                        'TECH_REVIEW_RETURNED', 'synthetic-v1')
                """,
                (uid(213), attempt_id, case_id, revision_id, content_hash),
            ),
            ("UPDATE agent_run SET purpose = 'verification' WHERE id = %s", (run_id,)),
            ("UPDATE expense SET request_amount = 999 WHERE id = %s", (expense_id,)),
            ("UPDATE authority_grant SET scope_data = '{}'::jsonb WHERE id = %s", (grant_id,)),
            (
                "UPDATE dossier_revision SET content_hash = %s WHERE id = %s",
                ("2" * 64, revision_id),
            ),
            (
                "UPDATE case_record SET current_state = 'EXECUTION', case_version = case_version + 1 WHERE id = %s",
                (terminal_case,),
            ),
            ("TRUNCATE TABLE event", ()),
            ("CREATE TABLE malicious_worker_escape (id integer)", ()),
        )
        for sql, params in attacks:
            rejects(db, sql, params)
    finally:
        db.execute("RESET ROLE")


def test_pls_retention_has_no_delete_before_tb28(db: psycopg.Connection) -> None:
    db.execute("SET ROLE pls_retention")
    try:
        can_delete = db.execute(
            "SELECT has_table_privilege('pls_retention', 'evidence', 'DELETE')"
        ).fetchone()
        assert can_delete == (False,)
    finally:
        db.execute("RESET ROLE")


def test_tb04a_dismissal_is_addressed_to_a_case(db: psycopg.Connection) -> None:
    """`DMV-4`: the dismissal row itself proves that a named case was dismissed."""
    case_id, other_case = uid(300), uid(301)
    insert_case(db, case_id)
    insert_case(db, other_case)

    dismissal_sql = """
        INSERT INTO pre_experiment_dismissal
          (id, case_id, original_request_ref, dismissed_at, stage, reason, applied_rule,
           actual_system_time_sec, disposition)
        VALUES (%s, %s, 'synthetic-request', now(), 'INTAKE', 'synthetic-reason',
                'R-SYNTHETIC', 12, 'synthetic-disposition')
    """
    db.execute(dismissal_sql, (uid(302), case_id))

    # UNIQUE(case_id): at most one administrative disposition per case.
    rejects(db, dismissal_sql, (uid(303), case_id))
    # NOT NULL: an unaddressed dismissal proves nothing about any case.
    rejects(
        db,
        """
        INSERT INTO pre_experiment_dismissal
          (id, original_request_ref, dismissed_at, stage, reason, applied_rule,
           actual_system_time_sec, disposition)
        VALUES (%s, 'synthetic-request', now(), 'INTAKE', 'synthetic-reason',
                'R-SYNTHETIC', 12, 'synthetic-disposition')
        """,
        (uid(304),),
    )
    # FK: the addressed case must exist.
    rejects(db, dismissal_sql, (uid(305), uid(399)))
    # Append-only stays in force after the erratum.
    rejects(
        db,
        "UPDATE pre_experiment_dismissal SET case_id = %s WHERE case_id = %s",
        (other_case, case_id),
    )
    rejects(db, "DELETE FROM pre_experiment_dismissal WHERE case_id = %s", (case_id,))


def test_tb04a_genesis_is_the_only_transition_without_a_source_state(
    db: psycopg.Connection,
) -> None:
    """`DMV-5`: `from_state IS NULL` is admissible for case creation alone."""
    genesis_case, foreign_case = uid(310), uid(311)
    for case_id in (genesis_case, foreign_case):
        db.execute(
            """
            INSERT INTO case_record (id, current_state, case_version, depth_level, timezone)
            VALUES (%s, 'INTAKE', 0, 'std', 'UTC')
            """,
            (case_id,),
        )
    genesis_event, foreign_event = uid(312), uid(313)
    for event_id, case_id in ((genesis_event, genesis_case), (foreign_event, foreign_case)):
        db.execute(
            """
            INSERT INTO event (id, case_id, type, actor_type, occurred_at)
            VALUES (%s, %s, 'CASE_SUBMITTED', 'user', now())
            """,
            (event_id, case_id),
        )

    insert_transition = """
        INSERT INTO state_transition
          (id, case_id, event_id, from_state, to_state, guard_results_ref,
           case_version_before, case_version_after)
        VALUES (%s, %s, %s, %s, %s, '[]', %s, %s)
    """
    db.execute(
        insert_transition,
        (uid(314), genesis_case, genesis_event, None, "INTAKE", 0, 1),
    )

    forbidden = (
        # A source state exists, so version 0 is not a genesis transition.
        (uid(315), foreign_case, foreign_event, "INTAKE", "CLARIFICATION", 0, 1),
        # Genesis may only target INTAKE — the entry state of `03`.
        (uid(316), foreign_case, foreign_event, None, "EXECUTION", 0, 1),
        # Beyond genesis a source state is mandatory.
        (uid(317), foreign_case, foreign_event, None, "INTAKE", 1, 2),
        # Versions advance by exactly one.
        (uid(318), foreign_case, foreign_event, "INTAKE", "CLARIFICATION", 1, 3),
    )
    for params in forbidden:
        rejects(db, insert_transition, params)

    assert db.execute(
        "SELECT count(*) FROM state_transition WHERE case_id = %s", (foreign_case,)
    ).fetchone() == (0,)


def test_tb04a_command_receipt_is_domain_wide_and_web_has_no_access(
    db: psycopg.Connection,
) -> None:
    """`DMV-6`: one domain effect per (command_type, idempotency_key), worker-only."""
    case_id = uid(320)
    insert_case(db, case_id)

    receipt_sql = """
        INSERT INTO command_receipt
          (id, command_type, idempotency_key, case_id, actor_type, outcome_ref, outcome_kind)
        VALUES (%s, %s, %s, %s, 'user', 'synthetic-outcome', %s)
    """
    db.execute(receipt_sql, (uid(321), "AcceptIntake", "synthetic-key", case_id, "applied"))
    # Same command, same key: the domain effect is already recorded.
    rejects(db, receipt_sql, (uid(322), "AcceptIntake", "synthetic-key", case_id, "rejected"))
    # A different command may reuse the key — the pair is what is unique.
    db.execute(
        receipt_sql, (uid(323), "CompleteClarification", "synthetic-key", case_id, "applied")
    )
    # A creating command has no case row yet, so case_id stays nullable.
    db.execute(
        """
        INSERT INTO command_receipt
          (id, command_type, idempotency_key, actor_type, outcome_ref, outcome_kind)
        VALUES (%s, 'SubmitOpportunity', 'synthetic-creation-key', 'user',
                'synthetic-outcome', 'applied')
        """,
        (uid(324),),
    )
    rejects(db, receipt_sql, (uid(325), "AcceptIntake", "synthetic-other", case_id, "unknown"))

    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert db.execute(
            "SELECT has_table_privilege('pls_web', 'command_receipt', %s)", (privilege,)
        ).fetchone() == (False,), f"pls_web must hold no {privilege} on command_receipt"
    for privilege, expected in (
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", False),
        ("DELETE", False),
    ):
        assert db.execute(
            "SELECT has_table_privilege('pls_worker', 'command_receipt', %s)", (privilege,)
        ).fetchone() == (expected,), f"pls_worker {privilege} on command_receipt must be {expected}"
