# Data

- `synthetic/` — fictional network, committed. Every company, person and event is invented. It is built so each path type (direct, bridge, stage, shared_room) and the "no warm path" case appears, which makes it the regression fixture for tests.
- `real/` — a real Notion export in the same shape. **Gitignored. Never commit it.** The pre-commit hook and CI both scan for emails and LinkedIn profile URLs.

Shape: one JSON array per file, keyed by the Notion property names of the People, Companies and Events databases. Relations are arrays of record ids. `targets.json` lists target companies with a priority (1 = highest) and a one-line why.
