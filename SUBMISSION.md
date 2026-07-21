# AutoOps Build Week Submission Notes

## Category

Developer Tools

## Project Description

AutoOps is a safety-first SRE knowledge hub for on-call engineers. It ingests local mock runbooks, tickets, alerts, and discussion summaries, then returns cited, timeline-aware answers with remediation suggestions, contradictions, gaps, and confidence signals.

The prototype focuses on the knowledge layer before automation. It demonstrates how scattered operational knowledge from Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack can be normalized into a searchable local hub without exposing real organizational data.

## Judging Path

Fastest CLI demo:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m autoops demo
```

Browser demo:

```bash
.venv/bin/python -m autoops ingest mock_data --db data/autoops.db --rebuild
.venv/bin/python -m autoops serve --host 127.0.0.1 --port 8000 --db data/autoops.db
```

Open:

```text
http://127.0.0.1:8000/demo
```

Docker demo:

```bash
docker build -t autoops .
docker run --rm -p 8000:8000 autoops
```

Open:

```text
http://127.0.0.1:8000/demo
```

## Under-3-Minute Demo Video Script

1. State the problem: SREs lose incident time searching runbooks, tickets, alerts, and Slack context.
2. Run `.venv/bin/python -m autoops demo`.
3. Point out cited sources, remediation warning, freshness notes, contradiction flags, gaps, and confidence.
4. Run `.venv/bin/python -m autoops refresh --connection all --trigger manual --db data/autoops.db`.
5. Query `Kafka consumer lag settlement replay restart` to show refreshed fixture connector knowledge.
6. Open `http://127.0.0.1:8000/demo` and show the browser flow.
7. Mention safety: secrets, external/customer emails, and sensitive payloads are blocked before storage.
8. Mention Codex/GPT-5.6: used for SDLC planning, implementation, tests, docs, mock data, and design trade-offs.

## Devpost Checklist

- Working project: yes.
- Category: Developer Tools.
- Public repository: include this repo URL, or share a private repo with `testing@devpost.com` and `build-week-event@openai.com`.
- License for public repo: MIT.
- README setup instructions: included.
- Sample data: `mock_data/` and `connector_fixtures/`.
- Demo video: record using the script above.
- `/feedback` Codex Session ID: run `/feedback` in the Codex session where most core functionality was built, then paste the returned ID into Devpost.

## Future Scope

The stable judging branch stops before Phase 3 automation. A separate branch, `feature/hybrid-search-experimental`, shows future retrieval work with opt-in hybrid search using SQLite FTS, local deterministic embeddings, and structured metadata boosts.
