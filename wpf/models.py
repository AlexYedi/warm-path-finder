"""Data contracts for the warm-path finder.

Input files mirror the Notion export shape of the Empire State pipeline
(People / Companies / Events), keyed by the real Notion property names, so a
real export can replace the synthetic data without touching the logic.
Relations are lists of record ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Event Status values that mean Alex was actually in the room.
ATTENDED_STATUSES = frozenset({"attended", "post_complete"})

ROLE_CONTEXTS = frozenset({"speaker", "host", "organizer", "attendee", "contact"})


class ContractError(ValueError):
    """Raised when an input record breaks the data contract."""


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    industry: tuple[str, ...] = ()
    funding_stage: str | None = None


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    date: date
    status: str

    @property
    def attended(self) -> bool:
        return self.status in ATTENDED_STATUSES


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    title: str
    company_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    role_context: frozenset[str] = field(default_factory=frozenset)
    notes: str = ""

    @property
    def is_contact(self) -> bool:
        """True when Alex has actually met this person (Role Context: contact)."""
        return "contact" in self.role_context


@dataclass(frozen=True)
class Target:
    company_id: str
    priority: int
    why: str


@dataclass(frozen=True)
class Network:
    people: dict[str, Person]
    companies: dict[str, Company]
    events: dict[str, Event]
    targets: list[Target]


def _require(row: dict, key: str, source: str):
    if key not in row or row[key] in (None, ""):
        raise ContractError(f"{source}: record {row.get('id', '?')} missing required field '{key}'")
    return row[key]


def _load_rows(path: Path) -> list[dict]:
    with path.open() as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ContractError(f"{path.name}: expected a JSON array of records")
    return rows


def load_network(data_dir: Path) -> Network:
    """Load and validate a network export. Fails loudly on any broken reference."""
    data_dir = Path(data_dir)

    companies: dict[str, Company] = {}
    for row in _load_rows(data_dir / "companies.json"):
        cid = _require(row, "id", "companies")
        companies[cid] = Company(
            id=cid,
            name=_require(row, "Company Name", "companies"),
            industry=tuple(row.get("Industry / Space") or ()),
            funding_stage=row.get("Funding Stage"),
        )

    events: dict[str, Event] = {}
    for row in _load_rows(data_dir / "events.json"):
        eid = _require(row, "id", "events")
        events[eid] = Event(
            id=eid,
            name=_require(row, "Event Name", "events"),
            date=date.fromisoformat(_require(row, "Event Date", "events")),
            status=_require(row, "Event Status", "events"),
        )

    people: dict[str, Person] = {}
    for row in _load_rows(data_dir / "people.json"):
        pid = _require(row, "id", "people")
        role_context = frozenset(row.get("Role Context") or ())
        unknown = role_context - ROLE_CONTEXTS
        if unknown:
            raise ContractError(f"people: {pid} has unknown Role Context {sorted(unknown)}")
        company_ids = tuple(row.get("Company") or ())
        event_ids = tuple(row.get("Events") or ())
        for ref in company_ids:
            if ref not in companies:
                raise ContractError(f"people: {pid} references unknown company {ref}")
        for ref in event_ids:
            if ref not in events:
                raise ContractError(f"people: {pid} references unknown event {ref}")
        people[pid] = Person(
            id=pid,
            name=_require(row, "Name", "people"),
            title=row.get("Current Title") or "",
            company_ids=company_ids,
            event_ids=event_ids,
            role_context=role_context,
            notes=row.get("Notes") or "",
        )

    targets: list[Target] = []
    for row in _load_rows(data_dir / "targets.json"):
        cid = _require(row, "company_id", "targets")
        if cid not in companies:
            raise ContractError(f"targets: unknown company {cid}")
        targets.append(Target(company_id=cid, priority=int(row.get("priority", 3)), why=row.get("why", "")))

    return Network(people=people, companies=companies, events=events, targets=targets)
