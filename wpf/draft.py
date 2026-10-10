"""Draft the ask for a warm path.

v0 uses deterministic templates. LLM drafting arrives with the eval suite, so
every model-written draft is scored against a rubric before it reaches review.
Every draft is born `needs_review`: nothing here sends anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Network, Target
from .paths import WarmPath

REVIEW_STATUS = "needs_review"


@dataclass(frozen=True)
class Draft:
    recipient_person_id: str
    subject: str
    body: str
    status: str = REVIEW_STATUS


def _first(name: str) -> str:
    return name.split()[0]


def draft_ask(path: WarmPath, target: Target, network: Network) -> Draft:
    company = network.companies[path.target_company_id].name
    to = network.people[path.to_person_id]
    event = network.events[path.event_id].name if path.event_id else None
    why = target.why.rstrip(".")

    if path.path_type == "bridge":
        via = network.people[path.via_person_id]
        return Draft(
            recipient_person_id=via.id,
            subject=f"Quick intro to {to.name} at {company}?",
            body=(
                f"Hi {_first(via.name)},\n\n"
                f"I saw you and {_first(to.name)} were both at {event}. "
                f"I'm looking closely at {company}: {why}. "
                f"Would you be comfortable introducing me to {_first(to.name)} ({to.title})? "
                f"Happy to send a two-line blurb you can forward.\n\nThanks,\nAlex"
            ),
        )

    if path.path_type == "direct":
        return Draft(
            recipient_person_id=to.id,
            subject=f"{company}: 15 minutes?",
            body=(
                f"Hi {_first(to.name)},\n\n"
                f"Hope you're well. I'm looking closely at {company}: {why}. "
                f"Would you have 15 minutes in the next couple of weeks to tell me how the team "
                f"thinks about it from the inside?\n\nThanks,\nAlex"
            ),
        )

    hook = (
        f"I caught your session at {event}"
        if path.path_type == "stage"
        else f"We were both at {event}, though I don't think we got to talk"
    )
    return Draft(
        recipient_person_id=to.id,
        subject=f"From {event}",
        body=(
            f"Hi {_first(to.name)},\n\n"
            f"{hook}. I'm looking closely at {company}: {why}. "
            f"Would you be open to a short conversation?\n\nThanks,\nAlex"
        ),
    )
