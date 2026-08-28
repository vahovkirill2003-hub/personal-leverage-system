"""T05 and the partial T01 coverage owed by TB-05: the transition protocol `17` §3.

Every fixture value is synthetic (`22` §0.3); no real personal data appears here.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from pathlib import Path
from threading import Barrier
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from pls.event_ledger import EventRecord, append_event
from pls.ids import is_uuid7, uuid7
from pls.state_machine import (
    CaseFacts,
    DiagnosticHoldActive,
    GuardOutcome,
    GuardRejected,
    OutboxIntent,
    TerminalLocked,
    TransitionCommand,
    TransitionRejected,
    UnknownState,
    VersionConflict,
    apply_transition,
    load_case_facts,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("PLS_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="PLS_TEST_DATABASE_URL is required for PostgreSQL transition tests",
)


@pytest.fixture(scope="module")
def migrated_database() -> str:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        config = Config(ROOT / "alembic.ini")
        command.upgrade(config, "head")
        yield TEST_DATABASE_URL
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture()
def db(migrated_database: str) -> psycopg.Connection:
    connection = psycopg.connect(migrated_database)
    yield connection
    connection.close()


def seed_case(connection: psycopg.Connection, *, state: str = "EXECUTION") -> UUID:
    """Insert one synthetic case just past genesis and return its id.

    `case_version = 1` is the first version a case can hold: version 0 exists
    only before the genesis transition, and the genesis CHECK of `14 v0.3` §3.3
    admits exactly one transition out of it — `from_state IS NULL` into `INTAKE`,
    written by the creation protocol `17 v0.2` §3.7 that TB-06 owns. A fixture
    seeding an arbitrary state at version 0 would describe a case the schema
    does not admit.
    """
    case_id = uuid7()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO case_record (id, current_state, case_version, depth_level, timezone)
            VALUES (%s, %s, 1, 'std', 'UTC')
            """,
            (case_id, state),
        )
    connection.commit()
    return case_id


def passing_guard(guard_id: str = "G_SYNTHETIC_PASS"):
    def guard(facts: CaseFacts, now) -> GuardOutcome:
        return GuardOutcome(
            guard_id=guard_id,
            passed=True,
            facts=(f"case_record:{facts.case_id}",),
        )

    return guard


def failing_guard(guard_id: str = "G_SYNTHETIC_FAIL"):
    def guard(facts: CaseFacts, now) -> GuardOutcome:
        return GuardOutcome(guard_id=guard_id, passed=False, reason="synthetic rejection")

    return guard


def count(connection: psycopg.Connection, sql: str, params: tuple[object, ...]) -> int:
    with connection.cursor() as cursor:
        return cursor.execute(sql, params).fetchone()[0]


def command_for(case_id: UUID, *, version: int = 1, to_state: str = "EVIDENCE_COLLECTION", **kw):
    return TransitionCommand(
        case_id=case_id,
        expected_case_version=version,
        event_type="SYNTHETIC_TRANSITION",
        actor_type="system",
        to_state=to_state,
        **kw,
    )


def test_protocol_commits_event_transition_and_projection_together(
    db: psycopg.Connection,
) -> None:
    case_id = seed_case(db)

    outcome = apply_transition(db, command_for(case_id, guards=(passing_guard(),)))

    assert outcome.from_state == "EXECUTION"
    assert outcome.to_state == "EVIDENCE_COLLECTION"
    assert outcome.case_version_before == 1
    assert outcome.case_version_after == 2
    assert is_uuid7(outcome.event_id) and is_uuid7(outcome.transition_id)

    with db.cursor() as cursor:
        facts = load_case_facts(cursor, case_id, lock=False)
    assert facts.current_state == "EVIDENCE_COLLECTION"
    assert facts.case_version == 2
    assert facts.current_status is None
    assert count(db, "SELECT count(*) FROM event WHERE id = %s", (outcome.event_id,)) == 1
    assert (
        count(
            db,
            "SELECT count(*) FROM state_transition WHERE id = %s",
            (outcome.transition_id,),
        )
        == 1
    )


def test_guard_verdicts_are_recorded_with_rule_version_and_fact_references(
    db: psycopg.Connection,
) -> None:
    case_id = seed_case(db)

    outcome = apply_transition(
        db, command_for(case_id, guards=(passing_guard("G20_WITHIN_TIMEBOX"),))
    )

    with db.cursor() as cursor:
        stored = cursor.execute(
            "SELECT guard_results_ref FROM state_transition WHERE id = %s",
            (outcome.transition_id,),
        ).fetchone()[0]
    assert stored == outcome.guard_results_ref
    assert '"guard_id":"G20_WITHIN_TIMEBOX"' in stored
    assert '"verdict":"pass"' in stored
    assert '"rule_version":"03-state-machine-v2"' in stored
    assert f'"facts":["case_record:{case_id}"]' in stored


def test_version_mismatch_is_a_conflict_and_leaves_no_effect(db: psycopg.Connection) -> None:
    case_id = seed_case(db)
    apply_transition(db, command_for(case_id))

    with pytest.raises(VersionConflict) as conflict:
        apply_transition(db, command_for(case_id, version=1))

    assert conflict.value.expected == 1
    assert conflict.value.facts.case_version == 2
    assert conflict.value.facts.current_state == "EVIDENCE_COLLECTION"
    assert count(db, "SELECT count(*) FROM state_transition WHERE case_id = %s", (case_id,)) == 1


def test_guard_rejection_aborts_the_whole_transaction(db: psycopg.Connection) -> None:
    case_id = seed_case(db)

    with pytest.raises(GuardRejected) as rejection:
        apply_transition(
            db,
            command_for(
                case_id,
                guards=(passing_guard(), failing_guard()),
                notifications=(
                    OutboxIntent(
                        logical_notification_id=f"synthetic-{case_id}",
                        kind="informational",
                        payload_ref="synthetic-ref",
                    ),
                ),
            ),
        )

    assert [o.guard_id for o in rejection.value.failed] == ["G_SYNTHETIC_FAIL"]
    assert count(db, "SELECT count(*) FROM event WHERE case_id = %s", (case_id,)) == 0
    assert count(db, "SELECT count(*) FROM state_transition WHERE case_id = %s", (case_id,)) == 0
    assert count(db, "SELECT count(*) FROM outbox WHERE case_id = %s", (case_id,)) == 0
    with db.cursor() as cursor:
        assert load_case_facts(cursor, case_id, lock=False).case_version == 1


def test_terminal_transition_sets_status_locks_case_and_releases_slot(
    db: psycopg.Connection,
) -> None:
    case_id = seed_case(db)
    with db.cursor() as cursor:
        # The slot holds exactly one row by construction; claim it for this case.
        cursor.execute("DELETE FROM active_experiment_slot WHERE user_scope = 'single-user'")
        cursor.execute(
            "INSERT INTO active_experiment_slot (user_scope, case_id) VALUES ('single-user', %s)",
            (case_id,),
        )
    db.commit()

    apply_transition(db, command_for(case_id, to_state="CLOSED_COUNTED"))

    with db.cursor() as cursor:
        facts = load_case_facts(cursor, case_id, lock=False)
    assert facts.current_status == "CLOSED_COUNTED"
    assert facts.terminal_locked_at is not None
    assert (
        count(db, "SELECT count(*) FROM active_experiment_slot WHERE case_id = %s", (case_id,)) == 0
    )

    with pytest.raises(TerminalLocked):
        apply_transition(db, command_for(case_id, version=2, to_state="EXECUTION"))


def test_paused_state_sets_status_without_terminal_lock(db: psycopg.Connection) -> None:
    case_id = seed_case(db)

    apply_transition(db, command_for(case_id, to_state="PAUSED_USER"))

    with db.cursor() as cursor:
        facts = load_case_facts(cursor, case_id, lock=False)
    assert facts.current_status == "PAUSED_USER"
    assert facts.terminal_locked_at is None


def test_diagnostic_hold_blocks_every_transition_without_exemption(
    db: psycopg.Connection,
) -> None:
    """`17` §5: a hold exempts no state transition, so no bypass may exist.

    The four exceptions of §5 either leave the case untouched
    (`RegisterLateEvidence`, read-only diagnostics), materialize an event
    without a transition (`FireTimer`), or change only the hold fields
    (`ExitDiagnosticHold`, owned by TB-11). None of them is a transition, so a
    command carrying an exemption flag would itself be the defect.
    """
    case_id = seed_case(db)
    with db.cursor() as cursor:
        # Entering a hold is itself a versioned write (`17` §5); TB-11 owns that
        # command, so the test reproduces the state it leaves behind.
        cursor.execute(
            """
            UPDATE case_record
            SET diagnostic_hold = true, case_version = case_version + 1
            WHERE id = %s
            """,
            (case_id,),
        )
    db.commit()

    assert "allowed_during_hold" not in {f.name for f in fields(TransitionCommand)}

    # Active, pause and terminal targets alike; a notification intent rides
    # along so the outbox is checked for a partial effect too (`17` §3.5).
    for target in ("EVIDENCE_COLLECTION", "PAUSED_USER", "CLOSED_COUNTED"):
        with pytest.raises(DiagnosticHoldActive):
            apply_transition(
                db,
                command_for(
                    case_id,
                    version=2,
                    to_state=target,
                    guards=(passing_guard(),),
                    notifications=(
                        OutboxIntent(
                            logical_notification_id=f"synthetic-hold-{case_id}-{target}",
                            kind="informational",
                            payload_ref="synthetic-ref",
                        ),
                    ),
                ),
            )

    assert count(db, "SELECT count(*) FROM state_transition WHERE case_id = %s", (case_id,)) == 0
    assert count(db, "SELECT count(*) FROM event WHERE case_id = %s", (case_id,)) == 0
    assert count(db, "SELECT count(*) FROM outbox WHERE case_id = %s", (case_id,)) == 0
    with db.cursor() as cursor:
        facts = load_case_facts(cursor, case_id, lock=False)
    assert facts.case_version == 2
    assert facts.current_state == "EXECUTION"
    assert facts.current_status is None
    assert facts.terminal_locked_at is None


def test_unknown_target_state_is_refused_before_any_write(db: psycopg.Connection) -> None:
    case_id = seed_case(db)

    with pytest.raises(UnknownState):
        apply_transition(db, command_for(case_id, to_state="NOT_IN_03"))

    assert count(db, "SELECT count(*) FROM event WHERE case_id = %s", (case_id,)) == 0


def test_missing_case_is_refused(db: psycopg.Connection) -> None:
    with pytest.raises(TransitionRejected):
        apply_transition(db, command_for(uuid7()))


def test_outbox_intent_commits_with_the_event(db: psycopg.Connection) -> None:
    case_id = seed_case(db)
    intent = OutboxIntent(
        logical_notification_id=f"synthetic-notification-{case_id}",
        kind="informational",
        payload_ref="synthetic-ref",
    )

    outcome = apply_transition(db, command_for(case_id, notifications=(intent,)))

    with db.cursor() as cursor:
        stored = cursor.execute(
            "SELECT created_tx_event_id FROM outbox WHERE id = %s", (intent.id,)
        ).fetchone()
    assert stored == (outcome.event_id,)


def test_history_is_append_only_for_the_runtime_role(db: psycopg.Connection) -> None:
    case_id = seed_case(db)
    outcome = apply_transition(db, command_for(case_id))

    with db.cursor() as cursor, pytest.raises(psycopg.Error):
        cursor.execute(
            "UPDATE state_transition SET to_state = 'EXECUTION' WHERE id = %s",
            (outcome.transition_id,),
        )
    db.rollback()

    with db.cursor() as cursor, pytest.raises(psycopg.Error):
        cursor.execute("DELETE FROM event WHERE id = %s", (outcome.event_id,))
    db.rollback()


def test_duplicate_version_for_a_case_is_rejected_by_the_database(
    db: psycopg.Connection,
) -> None:
    """(case_id, case_version_after) is UNIQUE, so no two transitions share a version."""
    case_id = seed_case(db)
    outcome = apply_transition(db, command_for(case_id))

    with db.cursor() as cursor:
        event_id = append_event(
            cursor,
            EventRecord(type="SYNTHETIC_DUPLICATE", actor_type="system", case_id=case_id),
        )
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO state_transition
                  (id, case_id, event_id, from_state, to_state, guard_results_ref,
                   case_version_before, case_version_after)
                VALUES (%s, %s, %s, 'EXECUTION', 'EVIDENCE_COLLECTION', '[]', 1, %s)
                """,
                (uuid7(), case_id, event_id, outcome.case_version_after),
            )
    db.rollback()


def test_concurrent_commands_produce_exactly_one_effect(migrated_database: str) -> None:
    """T05: a version race resolves to one transition; the loser gets a conflict."""
    setup = psycopg.connect(migrated_database)
    case_id = seed_case(setup)
    setup.close()

    barrier = Barrier(2)

    def attempt(target_state: str) -> str:
        connection = psycopg.connect(migrated_database)
        try:
            barrier.wait(timeout=10)
            apply_transition(connection, command_for(case_id, to_state=target_state))
            return "committed"
        except VersionConflict:
            return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(attempt, ("EVIDENCE_COLLECTION", "REVIEW_CONDITION_HANDLING")))

    assert results == ["committed", "conflict"]

    verify = psycopg.connect(migrated_database)
    try:
        assert (
            count(verify, "SELECT count(*) FROM state_transition WHERE case_id = %s", (case_id,))
            == 1
        )
        with verify.cursor() as cursor:
            assert load_case_facts(cursor, case_id, lock=False).case_version == 2
    finally:
        verify.close()
