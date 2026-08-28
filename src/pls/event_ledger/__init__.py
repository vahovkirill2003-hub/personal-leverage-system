"""Append-only event and audit ledger boundary.

The ledger only appends. It never updates or deletes history, and it never
decides whether a transition is allowed — that belongs to the state machine
(architecture §3.1). Every write here runs inside a transaction opened by the
caller so that event, transition, and projection update commit together
(`17` §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import psycopg

from pls.ids import uuid7

ACTOR_TYPES = frozenset({"user", "system", "agent_run", "timer", "admin"})


@dataclass(frozen=True)
class EventRecord:
    """One append-only row of `event` (`14` §3.3).

    `case_id` stays None only for security or system events raised outside a
    case, such as a rejected foreign callback.
    """

    type: str
    actor_type: str
    case_id: UUID | None = None
    actor_id: str | None = None
    occurred_at: datetime | None = None
    causation_id: UUID | None = None
    correlation_id: UUID | None = None
    payload_ref: str | None = None
    id: UUID = field(default_factory=uuid7)

    def __post_init__(self) -> None:
        if self.actor_type not in ACTOR_TYPES:
            raise ValueError(f"unknown actor_type: {self.actor_type}")
        if not self.type:
            raise ValueError("event type must not be empty")


@dataclass(frozen=True)
class StateTransitionRecord:
    """One append-only row of `state_transition` (`14` §3.3).

    Written only by the transaction that also updates `case_record`; the
    (case_id, case_version_after) uniqueness is enforced by the database.

    `from_state` is None only for the genesis transition of a case, which has no
    source state to name (`14 v0.3` §3.3, `17 v0.2` §3.7). The checks below
    mirror the database genesis CHECK so a malformed record is refused before it
    reaches append-only history; the database remains the enforcing authority.
    """

    case_id: UUID
    event_id: UUID
    from_state: str | None
    to_state: str
    guard_results_ref: str
    case_version_before: int
    case_version_after: int
    id: UUID = field(default_factory=uuid7)

    def __post_init__(self) -> None:
        if self.case_version_after <= self.case_version_before:
            raise ValueError("case_version_after must exceed case_version_before")
        if not self.guard_results_ref:
            raise ValueError("guard_results_ref must not be empty")
        if self.from_state is None:
            if self.case_version_before != 0 or self.case_version_after != 1:
                raise ValueError("genesis transition must move case_version 0 to 1")
            if self.to_state != "INTAKE":
                raise ValueError("genesis transition must target INTAKE")
        else:
            if self.case_version_before == 0:
                raise ValueError("only the genesis transition may start at case_version 0")
            if self.case_version_after != self.case_version_before + 1:
                raise ValueError("case_version must advance by exactly one")


def append_event(cursor: psycopg.Cursor, event: EventRecord) -> UUID:
    """Append one event and return its id.

    `occurred_at` falls back to the transaction clock so that stored times come
    from the database, never from a process clock (`14` §1.5).
    """
    cursor.execute(
        """
        INSERT INTO event
          (id, case_id, type, actor_type, actor_id, occurred_at,
           causation_id, correlation_id, payload_ref)
        VALUES (%s, %s, %s, %s, %s, COALESCE(%s, now()), %s, %s, %s)
        """,
        (
            event.id,
            event.case_id,
            event.type,
            event.actor_type,
            event.actor_id,
            event.occurred_at,
            event.causation_id,
            event.correlation_id,
            event.payload_ref,
        ),
    )
    return event.id


def append_state_transition(cursor: psycopg.Cursor, transition: StateTransitionRecord) -> UUID:
    """Append one state transition and return its id."""
    cursor.execute(
        """
        INSERT INTO state_transition
          (id, case_id, event_id, from_state, to_state, guard_results_ref,
           case_version_before, case_version_after)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            transition.id,
            transition.case_id,
            transition.event_id,
            transition.from_state,
            transition.to_state,
            transition.guard_results_ref,
            transition.case_version_before,
            transition.case_version_after,
        ),
    )
    return transition.id
