# warm-path-finder

Find the warmest route into a target account from the network you already have, and draft the ask for a human to approve.

## The problem

Cold outbound into AI-native companies mostly gets ignored. The network that would get a reply already exists: people you've met, people who were in the same room, people who spoke at events you attended. But that network sits across CRM records and event notes, and nobody turns it into a ranked list of asks. So the warm route gets missed, and the cold email goes out instead.

This tool reads a network export (people, companies, events), finds every warm path into each target company, ranks the paths, and drafts the ask. A person then approves each ask before it's sent. **Nothing in this repo sends anything.**

## How paths are ranked

Every score is two visible numbers multiplied together, and every path comes with a one-sentence reason. That way the person who has to act on a ranking can always see why.

| Path type | What it means | Weight |
|---|---|---|
| `direct` | You've met someone who works at the target | 1.0 |
| `bridge` | Someone you've met was in the same room as someone at the target: ask them for an intro | 0.6 |
| `stage` | Someone at the target spoke at, hosted or organized an event you attended | 0.4 |
| `shared_room` | Someone at the target attended an event you attended | 0.25 |

× **recency** of the most recent shared event: ≤90 days 1.0 · ≤180 days 0.8 · ≤365 days 0.6 · older 0.4.

Only events you actually attended count (`Event Status` of `attended` or `post_complete`). A target with no warm path gets flagged as a candidate for a second-degree search.

## Run it

Python 3.11+, standard library only.

```bash
python -m wpf --as-of 2026-10-09        # synthetic network -> out/
python -m unittest discover -s tests -v
```

Output:
- `out/outreach_sheet.csv`: one row per ask (target, rank, path type, score, who to send to, reason, status `needs_review`)
- `out/drafts.md`: the drafted asks, ready to review

To run on a real export, put it in `data/real/` (same shape as `data/synthetic/`, see `data/README.md`) and run `python -m wpf --data data/real`.

## Data safety

This repo is public, so it only ships synthetic data.

- `data/real/` and `out/` are gitignored.
- `scripts/pii_guard.sh` blocks any file containing an email address (other than example.com or noreply) or a LinkedIn profile URL, and blocks any path under `data/real/`. It runs as a pre-commit hook (enable it once with `git config core.hooksPath .githooks`) and again in CI on every file.
- Inputs come only from my own records: CRM, event notes, and enrichment from official APIs. There's no LinkedIn scraping.
- The tool stores *who could make an intro*. It doesn't store anyone's second-degree contact details.

## Roadmap

- [x] **v0**: data contracts, path finding + explainable ranking, template drafts, outreach sheet, tests, PII guard, CI
- [ ] Real run on my own network export, and the first intro asks sent
- [ ] Clay enrichment for second-degree paths on targets with no warm path
- [ ] LLM-drafted asks, scored by an eval suite (seed scenarios + rubric) that runs in CI
- [ ] `CASE.md`: the oversight design, eval results, outcomes, and what I'd change

## Architecture

```
data/<synthetic|real>/*.json  (Notion-shaped export)
        │  wpf/models.py   load + validate (fails loudly on broken references)
        ▼
     Network
        │  wpf/paths.py    find + score warm paths per target
        ▼
   WarmPath[]
        │  wpf/draft.py    draft the ask (status: needs_review)
        ▼
   out/outreach_sheet.csv · out/drafts.md   →   human review   →   send (manual)
```
