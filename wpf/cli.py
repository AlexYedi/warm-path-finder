"""Run the pipeline end to end: load -> find paths -> draft -> outreach sheet.

    python -m wpf                          # synthetic data -> out/
    python -m wpf --data data/real         # real export (gitignored)
    python -m wpf --as-of 2026-10-09       # pin the date for a reproducible run
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from .draft import draft_ask
from .models import load_network
from .paths import find_paths

SHEET_COLUMNS = [
    "target_priority", "target_company", "rank", "path_type", "score",
    "send_to", "about", "via", "reason", "subject", "status",
]


def run(data_dir: Path, out_dir: Path, as_of: date, top_n: int = 3) -> list[dict]:
    network = load_network(data_dir)
    paths_by_target = find_paths(network, as_of)

    rows: list[dict] = []
    drafts_md = [f"# Intro asks (needs review)\n\nRun as of {as_of.isoformat()}. Nothing is sent from this tool.\n"]

    for target in sorted(network.targets, key=lambda t: (t.priority, network.companies[t.company_id].name)):
        company = network.companies[target.company_id].name
        paths = paths_by_target[target.company_id][:top_n]
        drafts_md.append(f"\n## P{target.priority} · {company}\n")
        if not paths:
            drafts_md.append("_No warm path found. Candidate for Clay second-degree search._\n")
            rows.append({
                "target_priority": target.priority, "target_company": company, "rank": "",
                "path_type": "none", "score": 0, "send_to": "", "about": "", "via": "",
                "reason": "No warm path in current network", "subject": "", "status": "",
            })
            continue
        for rank, path in enumerate(paths, start=1):
            draft = draft_ask(path, target, network)
            recipient = network.people[draft.recipient_person_id].name
            about = network.people[path.to_person_id].name
            rows.append({
                "target_priority": target.priority,
                "target_company": company,
                "rank": rank,
                "path_type": path.path_type,
                "score": path.score,
                "send_to": recipient,
                "about": about,
                "via": network.people[path.via_person_id].name if path.via_person_id else "",
                "reason": path.reason,
                "subject": draft.subject,
                "status": draft.status,
            })
            drafts_md.append(
                f"\n### {rank}. {path.path_type} · score {path.score} · to {recipient}\n\n"
                f"_{path.reason}_\n\n**Subject:** {draft.subject}\n\n```\n{draft.body}\n```\n"
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "outreach_sheet.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "drafts.md").write_text("".join(drafts_md))
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wpf", description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args(argv)

    rows = run(args.data, args.out, args.as_of, args.top)
    targets = len({r["target_company"] for r in rows})
    found = len({r["target_company"] for r in rows if r["path_type"] != "none"})
    print(f"{targets} targets · {found} with a warm path · {sum(r['path_type'] != 'none' for r in rows)} asks drafted")
    print(f"-> {args.out / 'outreach_sheet.csv'}\n-> {args.out / 'drafts.md'}")
