# AutoOps

AutoOps is a safety-first SRE knowledge hub for on-call engineers. It reduces alert and ticket triage time by retrieving cited, timeline-aware operational context from scattered runbooks, tickets, alerts, and discussions.

This project was built with Codex using GPT-5.6 for the OpenAI Build Week Challenge.

## Build Week Submission

Category: **Developer Tools**

Best judging path:

```bash
.venv/bin/python -m autoops demo
```

Docker browser demo:

```bash
docker build -t autoops .
docker run --rm -p 8000:8000 autoops
```

Then open:

```text
http://127.0.0.1:8000/demo
```

Local browser demo:

```bash
.venv/bin/python -m autoops ingest mock_data --db data/autoops.db --rebuild
.venv/bin/python -m autoops serve --host 127.0.0.1 --port 8000 --db data/autoops.db
```

Then open:

```text
http://127.0.0.1:8000/demo
```

Current verification:

```text
Ran 59 tests

OK
```

## What It Does

On-call engineers often receive Jira tickets and PagerDuty alerts with incomplete or stale context. The right SOP may be in Confluence, GitLab Pages, Google Docs, a previous ticket, a PagerDuty note, or a Slack thread. AutoOps turns that scattered knowledge into a local, queryable hub.

The current prototype demonstrates:

- Manual ingestion of mock SRE knowledge from Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack-style files.
- CLI, API, and browser demo experiences.
- Cited query results with source path, source type, version, update time, and excerpts.
- Source-supported remediation suggestions with an explicit warning that they may be incomplete or incorrect.
- Timeline and freshness notes that prefer the newest retrieved context.
- Contradiction flags when matched sources disagree.
- Edge-case demo data for planned maintenance, access requests, production changes, deprecated guidance, and ownership/routing context.
- Safety checks that block secrets, external/customer email addresses, and sensitive-looking payloads before storage.
- Fixture-backed Confluence, GitLab, and Jira connectors that simulate source sync without calling live APIs.
- Hash-only raw source metadata storage for connector payloads by default.
- Containerized browser demo startup that rebuilds mock data before serving.
- Tests covering ingestion, querying, API behavior, safety, migrations, fixtures, connector sync, container packaging, and the judge demo.

## Why It Matters

For SRE teams, the cost of scattered knowledge is paid during incidents. A 15-30 minute search across docs, tickets, alerts, and Slack can consume a major portion of a 30-minute escalation window. AutoOps aims to compress that search into a single cited response so the engineer can spend more time monitoring, mitigating, and writing the RCA.

The project intentionally starts with retrieval and trust signals before automation. Later phases can triage tickets and alerts, but only after the knowledge layer can cite sources, track recency, block unsafe content, and flag contradictions.

## Demo Flow

Use this flow for the under-3-minute video:

1. Run the judge demo:

   ```bash
   .venv/bin/python -m autoops demo
   ```

2. Point out that AutoOps rebuilds the mock knowledge hub and queries an alert:

   ```text
   What should I do for HighKafkaConsumerLag in payments?
   ```

3. Show the output sections:

   - cited sources
   - recommended remediation steps
   - warning that remediation may be incorrect
   - timeline notes
   - contradiction flags
   - confidence and gaps

4. Show fixture connector sync:

   ```bash
   .venv/bin/python -m autoops refresh --connection all --trigger manual --db data/autoops.db
   ```

5. Query the newer synced runbook version:

   ```bash
   .venv/bin/python -m autoops query "Kafka consumer lag settlement replay restart" --db data/autoops.db
   ```

6. Show the browser demo at `http://127.0.0.1:8000/demo`.

7. Mention that unsafe content is blocked before it reaches the knowledge store.

8. Mention that the Docker path gives judges a dependency-light way to run the demo.

9. Mention that live connectors are intentionally guarded until account setup, token scopes, and source allowlists are approved.

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

AutoOps is a working, non-trivial local project with a CLI, FastAPI API, browser demo, Docker packaging, SQLite FTS search, schema migrations, fixture connector architecture, scheduled/manual refresh workflow, source citation model, contradiction detection, safety screening, and 59 automated tests.

**Design**

The project provides three runnable experiences: a judge demo command, CLI commands for realistic SRE workflows, and a browser demo for querying, ingestion, fixture refresh, and sync status. The output is organized around the way on-call engineers make decisions: answer, remediation, warning, sources, timeline, contradictions, gaps, and confidence.

**Potential Impact**

The target user is specific: on-call SREs and DevOps engineers handling tickets and alerts. The demonstrated workflow directly addresses the time lost searching Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack before mitigation can begin.

**Quality of the Idea**

AutoOps goes beyond basic document search by combining citation, timeline awareness, contradiction visibility, source-supported remediation, safety filtering, and a phased path toward agentic triage automation.

## Setup

The included workspace has a project-local `.venv` already configured. Use it for the quickest path:

```bash
.venv/bin/python -m autoops --help
```

Fresh local setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

No external data source accounts are required for the current demo. All runnable examples use local mock data and sanitized connector fixtures.

Supported platform:

- macOS/Linux with Python 3.11+ recommended.
- SQLite FTS5 support is required. The standard Python SQLite build on current macOS/Linux installations usually includes it.
- Docker, if using the containerized browser demo.

## Quickstart

Run the complete judge walkthrough:

```bash
.venv/bin/python -m autoops demo
```

Run the containerized browser demo:

```bash
docker build -t autoops .
docker run --rm -p 8000:8000 autoops
```

Open:

```text
http://127.0.0.1:8000/demo
```

Run the test suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Rebuild the static mock knowledge hub:

```bash
.venv/bin/python -m autoops ingest mock_data --db data/autoops.db --rebuild
```

Ask the primary alert-triage query:

```bash
.venv/bin/python -m autoops query "What should I do for HighKafkaConsumerLag in payments?" --db data/autoops.db
```

Run with JSON output:

```bash
.venv/bin/python -m autoops query "What should I do for HighKafkaConsumerLag in payments?" --db data/autoops.db --json
```

Validate a fixture connector without writing:

```bash
.venv/bin/python -m autoops sync confluence --dry-run
```

Sync individual fixture connectors:

```bash
.venv/bin/python -m autoops sync confluence --db data/autoops.db
.venv/bin/python -m autoops sync gitlab --db data/autoops.db
.venv/bin/python -m autoops sync jira --db data/autoops.db
```

Run the manual refresh workflow:

```bash
.venv/bin/python -m autoops refresh --connection all --trigger manual --db data/autoops.db
```

Run the cron-compatible scheduled refresh workflow:

```bash
.venv/bin/python -m autoops refresh --connection all --trigger scheduled --db data/autoops.db
```

Start the local API and browser demo:

```bash
.venv/bin/python -m autoops serve --host 127.0.0.1 --port 8000 --db data/autoops.db
```

Open:

```text
http://127.0.0.1:8000/demo
```

The Docker image runs the same local API. On startup it rebuilds `data/autoops.db` from `mock_data` before serving, so judges do not need to run a separate ingest command.

## Sample Queries

Core alert triage:

```bash
.venv/bin/python -m autoops query "What should I do for HighKafkaConsumerLag in payments?" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "DatabaseConnectionPoolSaturation in orders-api" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "SearchIndexMemoryPressure in search service" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "Who owns payments kafka consumer lag?" --db data/autoops.db
```

Experimental hybrid-search branch only:

```bash
.venv/bin/python -m autoops query "responsible team payments consumer backlog" --db data/autoops.db --search-mode hybrid --limit 3
```

Shows the future retrieval path: SQLite FTS + local deterministic embeddings + structured metadata boosts. Ownership questions are detected as ownership intent, so AutoOps returns the likely owning team first and avoids unrelated remediation steps.

```bash
.venv/bin/python -m autoops query "CheckoutLatencyHigh checkout api remediation" --db data/autoops.db
```

Edge-case demo queries:

```bash
.venv/bin/python -m autoops query "planned maintenance payments settlement replay" --db data/autoops.db
```

Shows planned maintenance context from a mock Google Docs maintenance calendar before escalating an alert-like symptom.

```bash
.venv/bin/python -m autoops query "access request payments runbook space" --db data/autoops.db
```

Shows a Jira access request that is not related to PagerDuty.

```bash
.venv/bin/python -m autoops query "production change checkout cache rollout latency" --db data/autoops.db
```

Shows a production change ticket plus related Slack discussion for a latency scenario.

```bash
.venv/bin/python -m autoops query "PaymentGatewayTimeoutRateHigh legacy timeout" --db data/autoops.db
```

Shows deprecated legacy guidance alongside the newer SOP and flags the deprecated source in timeline notes.

After fixture refresh:

```bash
.venv/bin/python -m autoops query "Kafka consumer lag settlement replay restart" --db data/autoops.db
```

## API

FastAPI endpoints:

- `GET /`
- `GET /demo`
- `GET /health`
- `POST /ingest`
- `POST /query`
- `POST /sync/confluence`
- `POST /sync/gitlab`
- `POST /sync/jira`
- `POST /refresh`
- `GET /sync/status`
- `GET /sources`
- `GET /sources/{source_id}`
- `GET /openapi-summary`
- `GET /docs`
- `GET /openapi.json`

Example API query:

```bash
python3 - <<'PY'
import json
from urllib.request import Request, urlopen

payload = json.dumps({
    "query": "What should I do for HighKafkaConsumerLag in payments?"
}).encode()

request = Request(
    "http://127.0.0.1:8000/query",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print(urlopen(request).read().decode())
PY
```

## Repository Layout

```text
autoops/
  CLI, API, demo, ingestion, query, safety, storage, migrations, and connector code.

autoops/connectors/
  Connector interface and fixture connectors.

connector_fixtures/
  Sanitized API-style fixture payloads for Confluence, GitLab, Google Drive, Google Docs, Jira, PagerDuty, and Slack.

data/
  Committed generated SQLite prototype database.

mock_data/
  Normalized mock source files for static ingestion.

Dockerfile
  Containerized browser demo startup.

requirements.txt
  Python runtime dependencies.

outputs/
  Design and acceptance-review deliverables.

tests/
  Unit and fixture tests.
```

## Data And Safety Model

Current local data sources:

- Mock Confluence runbooks and SOPs.
- Mock GitLab operational pages.
- Mock Google Docs-style SOPs.
- Mock Jira incidents, access requests, and production changes.
- Mock PagerDuty alerts/incidents.
- Mock Slack discussions.
- Sanitized connector fixtures for future source integrations.

Safety expectations:

- Customer PII should not be stored.
- Customer email addresses are blocked.
- Secrets, tokens, API keys, password-like assignments, bearer tokens, and private keys are blocked.
- Sensitive terminal output and real organizational data should not be ingested into this prototype.
- Operational team aliases or internal escalation emails may appear only when directly relevant to ownership or on-call routing.
- Live connector raw payloads default to hash-only storage; sanitized raw snapshots require explicit approval.

## Current Architecture

```text
Mock JSON / connector fixtures
  -> safety checks
  -> normalization
  -> SQLite documents/chunks
  -> SQLite FTS5 index
  -> CLI / FastAPI / browser demo
  -> cited answers, remediation, freshness notes, contradictions, gaps
```

Connector sync path:

```text
Connector fixture payload
  -> connector allowlist check
  -> raw source hash record
  -> normalized AutoOps document
  -> searchable index
  -> sync_state metadata
```

## Current Limitations

- No live external connectors are enabled yet.
- Scheduled refresh is implemented as a cron-compatible command, not a long-running daemon.
- No automated ticket or alert triage yet.
- No authentication or authorization on the local prototype API.
- Default querying uses SQLite FTS5 and heuristics. The `feature/hybrid-search-experimental` branch adds an opt-in local hybrid mode with deterministic embeddings and structured metadata boosts.
- Contradiction detection is conservative and rule-based.
- AutoOps flags contradictions but does not decide which source is correct.

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

Challenge Readiness Gate 1 is complete:

- Judge CLI demo.
- Local browser demo.
- README challenge packaging.

Challenge Readiness Gate 2 is complete:

- Dockerfile.
- requirements.txt.
- .dockerignore.
- Container packaging tests.

Next proposed implementation gate:

- Experimental Hybrid Search Gate: replace deterministic prototype embeddings with a production-grade local embedding model, evaluate retrieval quality, and decide whether the feature graduates into `main`.

No live API calls have been added yet. Before any real connector account setup is required, implementation must stop and ask the project owner to create or approve the platform account, workspace, token, scopes, and allowlist.

## Submission Checklist

- Working project: included.
- Category: Developer Tools.
- Project description: included above.
- Demo video: record using the demo flow above.
- Repository URL: add the public repo URL, or share a private repo with `testing@devpost.com` and `build-week-event@openai.com`.
- README setup instructions: included.
- Sample data: included in `mock_data/` and `connector_fixtures/`.
- Codex/GPT-5.6 usage explanation: included above.
- `/feedback` Codex Session ID: run `/feedback` in the Codex session used for the majority of core implementation and add the returned session ID to the Devpost submission.
- Developer tool testing path: use `.venv/bin/python -m autoops demo`, the Docker browser demo, or the local browser demo.
