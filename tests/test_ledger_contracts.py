"""Pure contracts of the ledger and guard model: no database required."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pls.event_ledger import EventRecord, StateTransitionRecord
from pls.ids import is_uuid7, uuid7
from pls.state_machine import (
    STATES,
    STATUS_STATES,
    TERMINAL_STATES,
    GuardOutcome,
    TransitionCommand,
    guard_policy_version,
    serialize_guard_results,
)

guard_ids = st.text(min_size=1, max_size=24).filter(lambda value: value.strip() != "")


@given(st.integers(min_value=0, max_value=2**48 - 1))
def test_generated_identifiers_satisfy_the_database_predicate(timestamp_ms: int) -> None:
    assert is_uuid7(uuid7(timestamp_ms=timestamp_ms))


def test_identifiers_are_time_ordered() -> None:
    earlier = uuid7(timestamp_ms=1_000)
    later = uuid7(timestamp_ms=2_000)
    assert earlier.bytes[:6] < later.bytes[:6]


def test_negative_timestamp_is_refused() -> None:
    with pytest.raises(ValueError):
        uuid7(timestamp_ms=-1)


@given(
    st.lists(
        st.tuples(guard_ids, st.booleans(), st.one_of(st.none(), st.text(max_size=32))),
        max_size=6,
    )
)
def test_guard_serialization_is_deterministic_and_replayable(raw: list) -> None:
    outcomes = [
        GuardOutcome(guard_id=guard_id, passed=passed, reason=reason)
        for guard_id, passed, reason in raw
    ]
    serialized = serialize_guard_results(outcomes)

    assert serialized == serialize_guard_results(outcomes)
    decoded = json.loads(serialized)
    assert [entry["guard_id"] for entry in decoded] == [o.guard_id for o in outcomes]
    assert [entry["verdict"] for entry in decoded] == [
        "pass" if o.passed else "reject" for o in outcomes
    ]


def test_guard_outcome_carries_facts_by_reference_only() -> None:
    outcome = GuardOutcome(
        guard_id="G28_EXPERIMENT_STARTABLE",
        passed=True,
        facts=("case_record:synthetic", "experiment_anchor:synthetic"),
    )
    record = outcome.as_record()
    assert record["facts"] == ["case_record:synthetic", "experiment_anchor:synthetic"]
    assert set(record) == {"guard_id", "rule_version", "facts", "verdict", "reason"}


def test_guard_policy_version_is_pinned_to_the_state_machine_baseline() -> None:
    assert guard_policy_version() == "03-state-machine-v2"


def test_the_environment_cannot_change_the_recorded_guard_policy_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`17` §2.3: guard semantics change only with a new version of `03`."""
    monkeypatch.setenv("PLS_GUARD_POLICY_VERSION", "03-state-machine-v3")

    assert guard_policy_version() == "03-state-machine-v2"

    outcome = GuardOutcome(guard_id="G20_WITHIN_TIMEBOX", passed=True)
    assert outcome.rule_version == "03-state-machine-v2"
    assert '"rule_version":"03-state-machine-v2"' in serialize_guard_results([outcome])


@pytest.mark.parametrize("rule_version", ["", "   ", "03-state-machine-v3", "custom"])
def test_guard_outcome_refuses_an_empty_or_foreign_rule_version(rule_version: str) -> None:
    with pytest.raises(ValueError):
        GuardOutcome(guard_id="G20_WITHIN_TIMEBOX", passed=True, rule_version=rule_version)


@pytest.mark.parametrize("guard_id", ["", "   "])
def test_guard_outcome_refuses_an_empty_guard_id(guard_id: str) -> None:
    with pytest.raises(ValueError):
        GuardOutcome(guard_id=guard_id, passed=True)


def test_state_sets_match_the_product_baseline() -> None:
    assert TERMINAL_STATES == {
        "CLOSED_COUNTED",
        "CLOSED_NOT_COUNTED",
        "REJECTED_BEFORE_EXECUTION",
    }
    assert STATUS_STATES == TERMINAL_STATES | {"PAUSED_USER", "PAUSED_EXTERNAL"}
    assert STATUS_STATES <= STATES
    assert "PRE_EXPERIMENT_DISMISSED" not in STATES


def test_event_rejects_an_unknown_actor_type() -> None:
    with pytest.raises(ValueError):
        EventRecord(type="SYNTHETIC", actor_type="robot")


def test_event_rejects_an_empty_type() -> None:
    with pytest.raises(ValueError):
        EventRecord(type="", actor_type="system")


def test_transition_requires_a_strictly_increasing_version() -> None:
    with pytest.raises(ValueError):
        StateTransitionRecord(
            case_id=uuid7(),
            event_id=uuid7(),
            from_state="EXECUTION",
            to_state="EVIDENCE_COLLECTION",
            guard_results_ref="[]",
            case_version_before=3,
            case_version_after=3,
        )


def test_transition_requires_recorded_guard_results() -> None:
    with pytest.raises(ValueError):
        StateTransitionRecord(
            case_id=uuid7(),
            event_id=uuid7(),
            from_state="EXECUTION",
            to_state="EVIDENCE_COLLECTION",
            guard_results_ref="",
            case_version_before=4,
            case_version_after=5,
        )


def test_genesis_transition_is_the_only_record_without_a_source_state() -> None:
    """`14 v0.3` §3.3: the record type mirrors the database genesis CHECK."""
    genesis = StateTransitionRecord(
        case_id=uuid7(),
        event_id=uuid7(),
        from_state=None,
        to_state="INTAKE",
        guard_results_ref="[]",
        case_version_before=0,
        case_version_after=1,
    )
    assert genesis.from_state is None

    forbidden = (
        # A source state exists, so version 0 is not a genesis transition.
        dict(from_state="INTAKE", to_state="CLARIFICATION", before=0, after=1),
        # Genesis may only target INTAKE.
        dict(from_state=None, to_state="EXECUTION", before=0, after=1),
        # Beyond genesis a source state is mandatory.
        dict(from_state=None, to_state="INTAKE", before=1, after=2),
        # Versions advance by exactly one.
        dict(from_state="INTAKE", to_state="CLARIFICATION", before=1, after=3),
    )
    for case in forbidden:
        with pytest.raises(ValueError):
            StateTransitionRecord(
                case_id=uuid7(),
                event_id=uuid7(),
                from_state=case["from_state"],
                to_state=case["to_state"],
                guard_results_ref="[]",
                case_version_before=case["before"],
                case_version_after=case["after"],
            )


def test_command_requires_an_expected_version_and_known_actor() -> None:
    with pytest.raises(ValueError):
        TransitionCommand(
            case_id=uuid7(),
            expected_case_version=-1,
            event_type="SYNTHETIC",
            actor_type="system",
            to_state="EXECUTION",
        )
    with pytest.raises(ValueError):
        TransitionCommand(
            case_id=uuid7(),
            expected_case_version=0,
            event_type="SYNTHETIC",
            actor_type="robot",
            to_state="EXECUTION",
        )
