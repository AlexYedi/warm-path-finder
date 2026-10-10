"""Export People / Companies / Events from Notion into the wpf input shape.

    python -m wpf.export_notion --targets data/real/targets_input.json

Reads NOTION_TOKEN and NOTION_DB_{PEOPLE,COMPANIES,EVENTS} from the
environment or a local .env (gitignored). Writes to data/real/ (gitignored).

Data minimization: only the fields the ranking uses are exported. Email,
phone, LinkedIn URL and bio text never leave Notion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Only these properties are exported. Everything else stays in Notion.
FIELDS = {
    "people": {"Name": "title", "Current Title": "rich_text", "Company": "relation",
               "Events": "relation", "Role Context": "multi_select"},
    "companies": {"Company Name": "title", "Industry / Space": "multi_select", "Funding Stage": "select"},
    "events": {"Event Name": "title", "Event Date": "date", "Event Status": "select"},
}


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def query_all(database_id: str, token: str) -> list[dict]:
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _request("POST", f"{API}/databases/{database_id}/query", token, body)
        pages.extend(data["results"])
        if not data.get("has_more"):
            return pages
        cursor = data["next_cursor"]


def _all_relation_ids(page_id: str, prop: dict, token: str) -> list[str]:
    """Relations are truncated at 25 inline; follow the property endpoint when has_more."""
    ids = [r["id"] for r in prop.get("relation", [])]
    if not prop.get("has_more"):
        return ids
    ids, cursor = [], None
    while True:
        url = f"{API}/pages/{page_id}/properties/{prop['id']}"
        if cursor:
            url += f"?start_cursor={cursor}"
        data = _request("GET", url, token)
        ids.extend(item["relation"]["id"] for item in data["results"])
        if not data.get("has_more"):
            return ids
        cursor = data["next_cursor"]


def convert_value(prop: dict, kind: str, page_id: str = "", token: str = ""):
    """Turn one Notion API property into a plain value."""
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in prop.get(kind, [])).strip()
    if kind == "multi_select":
        return [o["name"] for o in prop.get("multi_select", [])]
    if kind == "select":
        return (prop.get("select") or {}).get("name")
    if kind == "date":
        start = (prop.get("date") or {}).get("start")
        return start[:10] if start else None
    if kind == "relation":
        return _all_relation_ids(page_id, prop, token) if token else [r["id"] for r in prop.get("relation", [])]
    raise ValueError(f"unsupported property type {kind}")


def convert_pages(pages: list[dict], fields: dict[str, str], token: str = "") -> list[dict]:
    rows = []
    for page in pages:
        if page.get("archived") or page.get("in_trash"):
            continue
        row = {"id": page["id"]}
        for name, kind in fields.items():
            prop = page["properties"].get(name)
            if prop is None:
                raise KeyError(f"Notion schema drift: property '{name}' missing")
            if prop["type"] != kind:
                raise TypeError(f"Notion schema drift: '{name}' is {prop['type']}, expected {kind}")
            row[name] = convert_value(prop, kind, page["id"], token)
        rows.append(row)
    return rows


def normalize(name: str) -> str:
    name = re.sub(r"\(.*?\)", "", name.lower())
    name = re.sub(r"[^a-z0-9 ]", "", name)
    words = [w for w in name.split() if w not in {"ai", "labs", "inc", "the", "hq"}]
    return " ".join(words)


def clean(people: list[dict], companies: list[dict], events: list[dict]) -> tuple[list, list, list, dict]:
    """Drop records the contract can't accept and strip dangling references. Report counts."""
    report = {}
    events_ok = [e for e in events if e["Event Name"] and e["Event Date"] and e["Event Status"]]
    report["events_dropped_missing_name_date_or_status"] = len(events) - len(events_ok)
    companies_ok = [c for c in companies if c["Company Name"]]
    report["companies_dropped_missing_name"] = len(companies) - len(companies_ok)
    event_ids = {e["id"] for e in events_ok}
    company_ids = {c["id"] for c in companies_ok}

    people_ok, dangling = [], 0
    for p in people:
        if not p["Name"]:
            continue
        before = len(p["Company"]) + len(p["Events"])
        p["Company"] = [c for c in p["Company"] if c in company_ids]
        p["Events"] = [e for e in p["Events"] if e in event_ids]
        dangling += before - len(p["Company"]) - len(p["Events"])
        p["Role Context"] = [r for r in p["Role Context"] if r]
        people_ok.append(p)
    report["people_dropped_missing_name"] = len(people) - len(people_ok)
    report["dangling_references_removed"] = dangling
    return people_ok, companies_ok, events_ok, report


def resolve_targets(target_input: list[dict], companies: list[dict]) -> tuple[list[dict], list[dict]]:
    """Match target names to Companies records. Unmatched targets become placeholder
    companies, so they appear in the sheet as 'no warm path' instead of vanishing."""
    by_norm: dict[str, str] = {}
    for c in companies:
        by_norm.setdefault(normalize(c["Company Name"]), c["id"])
    targets, placeholders = [], []
    for t in target_input:
        names = [t["name"], *t.get("aliases", [])]
        cid = next((by_norm[normalize(n)] for n in names if normalize(n) in by_norm), None)
        if cid is None:
            cid = f"unmatched:{normalize(t['name']).replace(' ', '-')}"
            placeholders.append({"id": cid, "Company Name": t["name"], "Industry / Space": [], "Funding Stage": None})
        targets.append({"company_id": cid, "priority": t["priority"], "why": t.get("why", ""), "name": t["name"]})
    return targets, placeholders


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wpf.export_notion")
    parser.add_argument("--targets", type=Path, required=True, help="JSON list of {name, priority, why, aliases?}")
    parser.add_argument("--out", type=Path, default=Path("data/real"))
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        token = os.environ["NOTION_TOKEN"]
        dbs = {k: os.environ[f"NOTION_DB_{k.upper()}"] for k in FIELDS}
    except KeyError as missing:
        sys.exit(f"missing env var {missing}; see README")

    raw = {k: query_all(db, token) for k, db in dbs.items()}
    people = convert_pages(raw["people"], FIELDS["people"], token)
    companies = convert_pages(raw["companies"], FIELDS["companies"], token)
    events = convert_pages(raw["events"], FIELDS["events"], token)
    people, companies, events, report = clean(people, companies, events)

    targets, placeholders = resolve_targets(json.loads(args.targets.read_text()), companies)
    companies.extend(placeholders)

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("people", people), ("companies", companies), ("events", events), ("targets", targets)):
        (args.out / f"{name}.json").write_text(json.dumps(rows, indent=1))

    report.update({
        "people": len(people), "companies": len(companies) - len(placeholders), "events": len(events),
        "targets": len(targets), "targets_unmatched_in_notion": [p["Company Name"] for p in placeholders],
    })
    (args.out / "export_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
