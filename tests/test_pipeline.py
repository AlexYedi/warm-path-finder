"""Regression tests against the synthetic network.

The fixture is built so each path type appears; these tests pin the ranking
it must produce. Run: python -m unittest -v
"""

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from wpf.cli import run
from wpf.draft import REVIEW_STATUS, draft_ask
from wpf.models import ContractError, load_network
from wpf.paths import find_paths, recency_factor

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
AS_OF = date(2026, 10, 9)


class PathRanking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = load_network(DATA)
        cls.paths = find_paths(cls.network, AS_OF)

    def top(self, cid):
        return self.paths[cid][0]

    def test_direct_contact_ranks_first(self):
        top = self.top("c-01")
        self.assertEqual((top.path_type, top.to_person_id, top.score), ("direct", "p-01", 1.0))

    def test_bridge_beats_cold_shared_room(self):
        top = self.top("c-02")
        self.assertEqual((top.path_type, top.via_person_id, top.to_person_id), ("bridge", "p-04", "p-03"))

    def test_bridge_beats_stage_when_recency_equal(self):
        types = [p.path_type for p in self.paths["c-03"]]
        self.assertEqual(types, ["bridge", "stage"])

    def test_unattended_event_creates_no_path(self):
        self.assertEqual(self.paths["c-04"], [])

    def test_old_event_decays(self):
        self.assertAlmostEqual(self.top("c-06").score, 0.6 * 0.4)

    def test_contact_at_target_is_never_a_bridge_to_colleague(self):
        for p in self.paths["c-01"]:
            self.assertNotEqual(p.via_person_id, "p-01")

    def test_recency_bands(self):
        self.assertEqual(recency_factor(date(2026, 9, 1), AS_OF), 1.0)
        self.assertEqual(recency_factor(date(2026, 5, 1), AS_OF), 0.8)
        self.assertEqual(recency_factor(date(2025, 12, 1), AS_OF), 0.6)
        self.assertEqual(recency_factor(date(2024, 1, 1), AS_OF), 0.4)


class Drafting(unittest.TestCase):
    def test_bridge_ask_goes_to_the_connector(self):
        network = load_network(DATA)
        path = find_paths(network, AS_OF)["c-02"][0]
        target = next(t for t in network.targets if t.company_id == "c-02")
        draft = draft_ask(path, target, network)
        self.assertEqual(draft.recipient_person_id, "p-04")
        self.assertIn("Dana", draft.body)
        self.assertEqual(draft.status, REVIEW_STATUS)


class EndToEnd(unittest.TestCase):
    def test_run_writes_sheet_with_every_target_and_nothing_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run(DATA, out, AS_OF)
            with (out / "outreach_sheet.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual({r["target_company"] for r in rows}, {
                "Northwind Models", "Halcyon Data", "Lattice Agents", "Quarry Labs", "Tessellate",
            })
            self.assertTrue(all(r["status"] in ("", REVIEW_STATUS) for r in rows))
            self.assertTrue((out / "drafts.md").read_text().startswith("# Intro asks (needs review)"))


class Contracts(unittest.TestCase):
    def test_broken_reference_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ("companies", "events", "targets"):
                (tmp / f"{name}.json").write_text((DATA / f"{name}.json").read_text())
            people = json.loads((DATA / "people.json").read_text())
            people[0]["Company"] = ["c-missing"]
            (tmp / "people.json").write_text(json.dumps(people))
            with self.assertRaises(ContractError):
                load_network(tmp)


if __name__ == "__main__":
    unittest.main()
