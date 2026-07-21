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

## How Codex And GPT-5.6 Were Used

Codex with GPT-5.6 accelerated both product thinking and implementation:

- Converted the original on-call/SRE problem statement into a phased SDLC plan.
- Helped choose a no-cost prototype stack: Python, SQLite FTS5, FastAPI, standard-library CLI, and fixture data.
- Designed the schema, migration path, source metadata model, and connector interface.
- Built the ingestion pipeline, query engine, API, CLI, browser demo, refresh workflow, and fixture connectors.
- Added safety gates for secrets, PII-like content, and sensitive operational payloads.
- Generated mock data and connector fixtures for realistic SRE scenarios, including contradictions, stale runbooks, archived records, non-PagerDuty Jira tickets, and Slack context.
- Wrote and iterated tests at each gate, using failures to tighten the implementation.
- Preserved a gated development workflow so higher-risk automation and live integrations do not appear before safety and review controls exist.

Key decisions made during the Codex session:

- Use mock data first to avoid exposing organizational data.
- Store connector raw payloads as hashes by default, not full raw API payloads.
- Treat Jira as an independent source, not only as a PagerDuty artifact.
- Flag contradictions instead of deciding which source is correct.
- Require explicit human setup before any real connector account, token, scope, workspace, or allowlist is used.

## Judging Criteria Mapping

**Technological Implementation**

AutoOps is a working, non-trivial local project with a CLI, FastAPI API, browser demo, Docker packaging, SQLite FTS search, schema migrations, fixture connector architecture, scheduled/manual refresh workflow, source citation model, contradiction detection, safety screening, and automated tests.

**Design**

The project provides three runnable experiences: a judge demo command, CLI commands for realistic SRE workflows, and a browser demo for querying, ingestion, fixture refresh, and sync status. The output is organized around the way on-call engineers make decisions: answer, remediation, warning, sources, timeline, contradictions, gaps, and confidence.

**Potential Impact**

The target user is specific: on-call SREs and DevOps engineers handling tickets and alerts. The demonstrated workflow directly addresses the time lost searching Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack before mitigation can begin.

**Quality of the Idea**

AutoOps goes beyond basic document search by combining citation, timeline awareness, contradiction visibility, source-supported remediation, safety filtering, and a phased path toward agentic triage automation.

## Verification Record

Stable judging branch, `main`:

```text
Ran 57 tests

OK
```

Experimental branch, `feature/hybrid-search-experimental`:

```text
Ran 59 tests

OK
```

Notes:

- The stable branch is the recommended judging branch.
- Dockerfile packaging is covered by automated tests.
- A local Docker build may require Docker daemon access on the reviewer machine.

## SDLC Status

Phase 1 is complete:

- Design document.
- Prototype scaffold.
- Manual ingestion MVP.
- Query MVP.
- API MVP.
- Contradiction and freshness MVP.
- Expanded tests and acceptance review.

Phase 2 is complete:

- Phase 2 design approval.
- Schema migration foundation.
- Connector fixture framework.
- Confluence fixture connector.
- Manual refresh command and cron-compatible scheduled refresh command.
- Per-connector refresh locks.
- API sync status endpoint.
- GitLab fixture connector.
- Jira fixture connector.
- Phase 2 acceptance review.

Challenge readiness is complete:

- Judge CLI demo.
- Local browser demo.
- README challenge packaging.
- Dockerfile.
- requirements.txt.
- .dockerignore.
- Container packaging tests.
- Submission notes.

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

Next proposed implementation gates:

- Phase 3 Gate 1: event-triggered agent design.
- Hybrid search evaluation: replace deterministic prototype embeddings with a production-grade local embedding model, evaluate retrieval quality, and decide whether the feature graduates into `main`.

No live API calls have been added yet. Before any real connector account setup is required, implementation must stop and ask the project owner to create or approve the platform account, workspace, token, scopes, and allowlist.
