"""Find and rank warm paths into each target company.

Every score is a product of two visible numbers (path-type weight x recency),
and every path carries a plain-language reason, so a ranking can always be
explained to the person who has to act on it.

Path types, warmest first:
  direct      Alex has met someone who works at the target (Role Context: contact).
  bridge      Alex has met someone (not at the target) who was in the same room
              as someone at the target -> ask the contact for an intro.
  stage       Someone at the target spoke at / hosted / organized an event Alex
              attended -> a reason to reach out referencing their talk.
  shared_room Someone at the target attended an event Alex attended.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Event, Network, Person

PATH_WEIGHTS = {
    "direct": 1.0,
    "bridge": 0.6,
    "stage": 0.4,
    "shared_room": 0.25,
}

STAGE_ROLES = frozenset({"speaker", "host", "organizer"})


def recency_factor(event_date: date, as_of: date) -> float:
    """Decay by age of the most recent shared moment."""
    age = (as_of - event_date).days
    if age <= 90:
        return 1.0
    if age <= 180:
        return 0.8
    if age <= 365:
        return 0.6
    return 0.4


@dataclass(frozen=True)
class WarmPath:
    target_company_id: str
    path_type: str
    to_person_id: str
    via_person_id: str | None
    event_id: str | None
    score: float
    reason: str


def _attended_events(person: Person, network: Network) -> list[Event]:
    return [network.events[e] for e in person.event_ids if network.events[e].attended]


def _latest(events: list[Event]) -> Event:
    return max(events, key=lambda e: (e.date, e.id))


def find_paths(network: Network, as_of: date) -> dict[str, list[WarmPath]]:
    """Return every warm path per target company id, best first."""
    results: dict[str, list[WarmPath]] = {}
    contacts = [p for p in network.people.values() if p.is_contact]

    for target in network.targets:
        cid = target.company_id
        company = network.companies[cid]
        insiders = [p for p in network.people.values() if cid in p.company_ids]
        paths: list[WarmPath] = []

        for insider in insiders:
            shared = _attended_events(insider, network)

            if insider.is_contact:
                anchor = _latest(shared) if shared else None
                recency = recency_factor(anchor.date, as_of) if anchor else 0.6
                where = f"; last together at {anchor.name}" if anchor else ""
                paths.append(WarmPath(
                    cid, "direct", insider.id, None, anchor.id if anchor else None,
                    round(PATH_WEIGHTS["direct"] * recency, 3),
                    f"You know {insider.name}, {insider.title} at {company.name}{where}.",
                ))
                continue

            if not shared:
                continue

            for contact in contacts:
                if contact.id == insider.id or cid in contact.company_ids:
                    continue
                overlap = [e for e in shared if e.id in contact.event_ids]
                if not overlap:
                    continue
                anchor = _latest(overlap)
                paths.append(WarmPath(
                    cid, "bridge", insider.id, contact.id, anchor.id,
                    round(PATH_WEIGHTS["bridge"] * recency_factor(anchor.date, as_of), 3),
                    f"{contact.name} (you know them) and {insider.name} were both at {anchor.name}.",
                ))

            anchor = _latest(shared)
            if insider.role_context & STAGE_ROLES:
                role = sorted(insider.role_context & STAGE_ROLES)[0]
                paths.append(WarmPath(
                    cid, "stage", insider.id, None, anchor.id,
                    round(PATH_WEIGHTS["stage"] * recency_factor(anchor.date, as_of), 3),
                    f"{insider.name} was a {role} at {anchor.name}, which you attended.",
                ))
            else:
                paths.append(WarmPath(
                    cid, "shared_room", insider.id, None, anchor.id,
                    round(PATH_WEIGHTS["shared_room"] * recency_factor(anchor.date, as_of), 3),
                    f"You and {insider.name} were both at {anchor.name}.",
                ))

        paths.sort(key=lambda p: (-p.score, p.path_type, p.to_person_id, p.via_person_id or ""))
        results[cid] = paths

    return results
