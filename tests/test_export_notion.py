"""Exporter tests on synthetic Notion API-shaped pages (no network)."""

import unittest

from wpf.export_notion import FIELDS, clean, convert_pages, normalize, resolve_targets


def _text(kind, value):
    return {"type": kind, kind: [{"plain_text": value}]}


def person_page(pid, name, company_ids, event_ids, roles, email="someone@example.com"):
    return {
        "id": pid,
        "archived": False,
        "properties": {
            "Name": _text("title", name),
            "Current Title": _text("rich_text", "AE"),
            "Company": {"type": "relation", "relation": [{"id": c} for c in company_ids], "has_more": False},
            "Events": {"type": "relation", "relation": [{"id": e} for e in event_ids], "has_more": False},
            "Role Context": {"type": "multi_select", "multi_select": [{"name": r} for r in roles]},
            "Email": {"type": "email", "email": email},
        },
    }


class Convert(unittest.TestCase):
    def test_only_whitelisted_fields_are_exported(self):
        rows = convert_pages([person_page("p1", "Ada Lane", ["c1"], ["e1"], ["contact"])], FIELDS["people"])
        self.assertNotIn("Email", rows[0])
        self.assertEqual(rows[0]["Name"], "Ada Lane")
        self.assertEqual(rows[0]["Company"], ["c1"])

    def test_schema_drift_fails_loudly(self):
        page = person_page("p1", "Ada Lane", [], [], [])
        page["properties"]["Role Context"] = {"type": "select", "select": None}
        with self.assertRaises(TypeError):
            convert_pages([page], FIELDS["people"])

    def test_archived_pages_skipped(self):
        page = person_page("p1", "Ada Lane", [], [], [])
        page["archived"] = True
        self.assertEqual(convert_pages([page], FIELDS["people"]), [])


class Clean(unittest.TestCase):
    def test_dangling_refs_and_dateless_events_removed(self):
        people = [{"id": "p1", "Name": "Ada", "Current Title": "", "Company": ["c1", "gone"], "Events": ["e1", "e2"], "Role Context": []}]
        companies = [{"id": "c1", "Company Name": "Acme"}]
        events = [
            {"id": "e1", "Event Name": "Meetup", "Event Date": "2026-09-01", "Event Status": "attended"},
            {"id": "e2", "Event Name": "No date", "Event Date": None, "Event Status": "attended"},
        ]
        people, _, events, report = clean(people, companies, events)
        self.assertEqual(people[0]["Company"], ["c1"])
        self.assertEqual(people[0]["Events"], ["e1"])
        self.assertEqual(report["events_dropped_missing_name_date_or_status"], 1)
        self.assertEqual(report["dangling_references_removed"], 2)


class Targets(unittest.TestCase):
    def test_normalize_handles_suffixes_and_parentheses(self):
        self.assertEqual(normalize("Modal Labs"), normalize("Modal"))
        self.assertEqual(normalize("Cursor (Anysphere)"), "cursor")
        self.assertNotEqual(normalize("Scaled Cognition"), normalize("Cognition"))

    def test_unmatched_target_becomes_placeholder_not_dropped(self):
        companies = [{"id": "c1", "Company Name": "Modal Labs"}]
        targets, placeholders = resolve_targets(
            [{"name": "Modal", "priority": 1}, {"name": "Nowhere Inc", "priority": 2}], companies)
        self.assertEqual(targets[0]["company_id"], "c1")
        self.assertTrue(targets[1]["company_id"].startswith("unmatched:"))
        self.assertEqual(placeholders[0]["Company Name"], "Nowhere Inc")


if __name__ == "__main__":
    unittest.main()
