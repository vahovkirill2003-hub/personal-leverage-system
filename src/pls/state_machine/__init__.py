"""Deterministic state-machine boundary.

This module owns the transactional transition protocol of `17` §3 and the guard
evaluation model of `17` §2. It is the only place allowed to propose a
normative transition (architecture §3.1). The registry of transitions and of
guards `G01`–`G28` belongs to `03` and is wired in a later task; what lives here
is the mechanism every transition must go through.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import psycopg

from pls.event_ledger import (
    ACTOR_TYPES,
    EventRecord,
    StateTransitionRecord,
    append_event,
    append_state_transition,
)
from pls.ids import uuid7

ACTIVE_STATES = frozenset(
    {
        "INTAKE",
        "CLARIFICATION",
        "FACT_UNKNOWN_MAPPING",
        "EXPERIMENT_PLANNING",
        "DOSSIER_ASSEMBLY",
        "TECHNICAL_REVIEW",
        "SYSTEM_ACCEPTANCE",
        "USER_ACCEPTANCE",
        "EXECUTION",
        "EVIDENCE_COLLECTION",
        "REVIEW_CONDITION_HANDLING",
        "EXPERIMENT_CLOSURE",
        "DECISION_UPDATE",
        "REWORK_REQUIRED",
        "REVALIDATION_REQUIRED",
        "TECHNICAL_REVIEW_ESCALATION",
    }
)
PAUSED_STATES = frozenset({"PAUSED_USER", "PAUSED_EXTERNAL"})
TERMINAL_STATES = frozenset({"CLOSED_COUNTED", "CLOSED_NOT_COUNTED", "REJECTED_BEFORE_EXECUTION"})
STATES = ACTIVE_STATES | PAUSED_STATES | TERMINAL_STATES
STATUS_STATES = PAUSED_STATES | TERMINAL_STATES

DEFAULT_GUARD_POLICY_VERSION = "03-state-machine-v2"


class TransitionRejected(Exception):
    """Base class for a refused command; no partial effect is ever committed."""


class VersionConflict(TransitionRejected):
    """`expected_case_version` did not match the locked row (`17` §3.2).

    The command is never reinterpreted against the newer version; the caller
    receives the current projection and decides for itself (`17` §8).
    """

    def __init__(self, expected: int, facts: CaseFacts) -> None:
        super().__init__(
            f"expected case_version {expected}, found {facts.case_version}",
        )
        self.expected = expected
        self.facts = facts


class TerminalLocked(TransitionRejected):
    """The case is terminal; only late evidence may still be recorded (`17` §7 I4)."""


class DiagnosticHoldActive(TransitionRejected):
    """A diagnostic hold blocks every case-changing command (`17` §5)."""


class GuardRejected(TransitionRejected):
    """At least one guard returned a negative verdict (`17` §2.4)."""

    def __init__(self, outcomes: Sequence[GuardOutcome]) -> None:
        self.outcomes = tuple(outcomes)
        self.failed = tuple(outcome for outcome in self.outcomes if not outcome.passed)
        reasons = ", ".join(f"{o.guard_id}: {o.reason or 'rejected'}" for o in self.failed)
        super().__init__(f"guard rejection: {reasons}")


class UnknownState(TransitionRejected):
    """The requested target state is not part of `03`."""


@dataclass(frozen=True)
class CaseFacts:
    """Canonical `case_record` row read under the transaction lock.

    Guards read these canonical values and the transaction clock only; derived
    views are never an input to an authority guard (`14` §6).
    """

    case_id: UUID
    current_state: str
    current_status: str | None
    case_version: int
    current_revision_id: UUID | None
    depth_level: str
    timezone: str
    terminal_locked_at: datetime | None
    diagnostic_hold: bool
    reason_event_id: UUID | None


def guard_policy_version() -> str:
    """Return the guard rule version (`17` §2.3).

    The version of the guard registry is bound to the version of `03`, and guard
    semantics may change only with a new version of `03` under baseline rules.
    That version is a property of the accepted baseline, not of a deployment, so
    no runtime input may set this value.
    """
    return DEFAULT_GUARD_POLICY_VERSION


@dataclass(frozen=True)
class GuardOutcome:
    """One guard verdict, recorded verbatim in `state_transition.guard_results_ref`.

    Facts are carried by reference (`17` §2.2): each entry names a canonical row
    the guard read, never a copy of its content.
    """

    guard_id: str
    passed: bool
    rule_version: str = field(default_factory=guard_policy_version)
    facts: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        # `17` §2.2 makes the guard id and the rule version mandatory parts of
        # every recorded verdict, and §2.3 admits exactly one registry version
        # while `03` stands at v2. An absent or foreign value is refused here
        # rather than written into append-only history.
        if not self.guard_id.strip():
            raise ValueError("guard_id must not be empty")
        if self.rule_version != DEFAULT_GUARD_POLICY_VERSION:
            raise ValueError(f"rule_version must be {DEFAULT_GUARD_POLICY_VERSION}")

    def as_record(self) -> dict[str, object]:
        return {
            "guard_id": self.guard_id,
            "rule_version": self.rule_version,
            "facts": list(self.facts),
            "verdict": "pass" if self.passed else "reject",
            "reason": self.reason,
        }


Guard = Callable[[CaseFacts, datetime], GuardOutcome]


@dataclass(frozen=True)
class OutboxIntent:
    """A notification intent committed by the same transaction (`17` §3.5)."""

    logical_notification_id: str
    kind: str
    payload_ref: str
    id: UUID = field(default_factory=uuid7)


@dataclass(frozen=True)
class TransitionCommand:
    """A command that asks for one normative transition.

    `expected_case_version` is mandatory for every command that changes the
    projection (`17` §1.1).
    """

    case_id: UUID
    expected_case_version: int
    event_type: str
    actor_type: str
    to_state: str
    guards: tuple[Guard, ...] = ()
    actor_id: str | None = None
    causation_id: UUID | None = None
    correlation_id: UUID | None = None
    payload_ref: str | None = None
    notifications: tuple[OutboxIntent, ...] = ()

    def __post_init__(self) -> None:
        if self.actor_type not in ACTOR_TYPES:
            raise ValueError(f"unknown actor_type: {self.actor_type}")
        if self.expected_case_version < 0:
            raise ValueError("expected_case_version must not be negative")


@dataclass(frozen=True)
class TransitionOutcome:
    """What the committed transaction produced."""

    case_id: UUID
    event_id: UUID
    transition_id: UUID
    from_state: str
    to_state: str
    case_version_before: int
    case_version_after: int
    guard_results_ref: str
    guard_outcomes: tuple[GuardOutcome, ...]


def serialize_guard_results(outcomes: Sequence[GuardOutcome]) -> str:
    """Serialize guard verdicts canonically for `guard_results_ref`.

    `14` §3.3 defines the field as rule, version, facts, and verdict per guard,
    and `17` §2.2 keeps only the read facts as references. Sorted keys and a
    stable separator make the value reproducible for replay checks.
    """
    return json.dumps(
        [outcome.as_record() for outcome in outcomes],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_case_facts(cursor: psycopg.Cursor, case_id: UUID, *, lock: bool = True) -> CaseFacts:
    """Read the canonical case row, taking a transaction-scoped lock (`17` §3.1)."""
    cursor.execute(
        f"""
        SELECT id, current_state, current_status, case_version, current_revision_id,
               depth_level, timezone, terminal_locked_at, diagnostic_hold, reason_event_id
        FROM case_record
        WHERE id = %s
        {"FOR UPDATE" if lock else ""}
        """,
        (case_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise TransitionRejected(f"case {case_id} does not exist")
    return CaseFacts(*row)


def apply_transition(
    connection: psycopg.Connection,
    command: TransitionCommand,
) -> TransitionOutcome:
    """Execute the transactional transition protocol of `17` §3.

    The steps run in the specified order inside a single transaction: lock the
    case row, check the expected version, check terminal lock and diagnostic
    hold, evaluate guards and record their verdicts, append event and
    transition, update the projection and its companions, commit. Any rejection
    aborts the whole transaction, so a partial effect cannot be observed
    (`17` §2.4, §8). Model and network calls never happen inside it.

    A diagnostic hold admits no transition whatsoever, so no command carries an
    exemption: of the four exceptions of `17` §5, `RegisterLateEvidence` and the
    read-only diagnostics leave the case untouched, `FireTimer` materializes an
    event without a transition, and `ExitDiagnosticHold` changes only the hold
    fields. None of them goes through this function; `ExitDiagnosticHold` is
    owned by TB-11 as its own transactional command.
    """
    if command.to_state not in STATES:
        raise UnknownState(f"state {command.to_state} is not defined by 03")

    with connection.transaction():
        with connection.cursor() as cursor:
            facts = load_case_facts(cursor, command.case_id)

            if facts.case_version != command.expected_case_version:
                raise VersionConflict(command.expected_case_version, facts)

            if facts.terminal_locked_at is not None:
                raise TerminalLocked(f"case {facts.case_id} is terminal and cannot transition")

            if facts.diagnostic_hold:
                raise DiagnosticHoldActive(f"case {facts.case_id} is under diagnostic hold")

            cursor.execute("SELECT now()")
            transaction_now: datetime = cursor.fetchone()[0]

            outcomes = tuple(guard(facts, transaction_now) for guard in command.guards)
            if any(not outcome.passed for outcome in outcomes):
                raise GuardRejected(outcomes)
            guard_results_ref = serialize_guard_results(outcomes)

            event_id = append_event(
                cursor,
                EventRecord(
                    type=command.event_type,
                    actor_type=command.actor_type,
                    case_id=command.case_id,
                    actor_id=command.actor_id,
                    occurred_at=transaction_now,
                    causation_id=command.causation_id,
                    correlation_id=command.correlation_id,
                    payload_ref=command.payload_ref,
                ),
            )
            version_after = facts.case_version + 1
            transition_id = append_state_transition(
                cursor,
                StateTransitionRecord(
                    case_id=command.case_id,
                    event_id=event_id,
                    from_state=facts.current_state,
                    to_state=command.to_state,
                    guard_results_ref=guard_results_ref,
                    case_version_before=facts.case_version,
                    case_version_after=version_after,
                ),
            )
            _update_projection(cursor, command, version_after)
            for notification in command.notifications:
                _append_outbox(cursor, command.case_id, event_id, notification)

    return TransitionOutcome(
        case_id=command.case_id,
        event_id=event_id,
        transition_id=transition_id,
        from_state=facts.current_state,
        to_state=command.to_state,
        case_version_before=facts.case_version,
        case_version_after=version_after,
        guard_results_ref=guard_results_ref,
        guard_outcomes=outcomes,
    )


def _update_projection(
    cursor: psycopg.Cursor,
    command: TransitionCommand,
    version_after: int,
) -> None:
    """Advance the case projection; release the slot when the case turns terminal."""
    status = command.to_state if command.to_state in STATUS_STATES else None
    terminal = command.to_state in TERMINAL_STATES
    cursor.execute(
        """
        UPDATE case_record
        SET current_state = %s,
            current_status = %s,
            case_version = %s,
            terminal_locked_at = CASE WHEN %s THEN now() ELSE terminal_locked_at END
        WHERE id = %s
        """,
        (command.to_state, status, version_after, terminal, command.case_id),
    )
    if terminal:
        cursor.execute("DELETE FROM active_experiment_slot WHERE case_id = %s", (command.case_id,))


def _append_outbox(
    cursor: psycopg.Cursor,
    case_id: UUID,
    event_id: UUID,
    notification: OutboxIntent,
) -> None:
    """Record a notification intent in the same transaction as the event."""
    cursor.execute(
        """
        INSERT INTO outbox
          (id, logical_notification_id, case_id, kind, payload_ref, created_tx_event_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            notification.id,
            notification.logical_notification_id,
            case_id,
            notification.kind,
            notification.payload_ref,
            event_id,
        ),
    )
