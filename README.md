# AutoOps

AutoOps is a safety-first SRE knowledge hub for on-call engineers. It retrieves cited, timeline-aware operational context from scattered runbooks, tickets, alerts, and discussions so engineers can spend less time searching and more time mitigating.

The current prototype runs fully locally with mock data and sanitized connector fixtures. No live Confluence, GitLab, Google Docs, Jira, PagerDuty, or Slack accounts are required.

## What It Does

AutoOps demonstrates:

- Manual ingestion of mock SRE knowledge from Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack-style files.
- CLI, FastAPI, and browser demo experiences.
- Cited query results with source path, source type, version, update time, and excerpts.
- Source-supported remediation suggestions with an explicit warning that they may be incomplete or incorrect.
- Timeline and freshness notes that prefer newer retrieved context.
- Contradiction flags when matched sources disagree.
- Edge-case data for planned maintenance, access requests, production changes, deprecated guidance, and ownership/routing context.
- Safety checks that block secrets, customer/external email addresses, and sensitive-looking payloads before storage.
- Fixture-backed Confluence, GitLab, and Jira connectors that simulate source sync without calling live APIs.
- Hash-only raw source metadata storage for connector payloads by default.
- Containerized browser demo startup that rebuilds mock data before serving.

## Quickstart

Create a project-local virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run the complete local demo:

```bash
.venv/bin/python -m autoops demo
```

Run the test suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Browser Demo

Start the local API and browser demo:

```bash
.venv/bin/python -m autoops ingest mock_data --db data/autoops.db --rebuild
.venv/bin/python -m autoops serve --host 127.0.0.1 --port 8000 --db data/autoops.db
```

Open:

```text
http://127.0.0.1:8000/demo
```

## Docker

```bash
docker build -t autoops .
docker run --rm -p 8000:8000 autoops
```

Open:

```text
http://127.0.0.1:8000/demo
```

The Docker image rebuilds `data/autoops.db` from `mock_data` on startup before serving the browser demo.

## CLI Examples

Rebuild the static mock knowledge hub:

```bash
.venv/bin/python -m autoops ingest mock_data --db data/autoops.db --rebuild
```

Query an alert:

```bash
.venv/bin/python -m autoops query "What should I do for HighKafkaConsumerLag in payments?" --db data/autoops.db
```

Return JSON:

```bash
.venv/bin/python -m autoops query "What should I do for HighKafkaConsumerLag in payments?" --db data/autoops.db --json
```

Validate a fixture connector without writing:

```bash
.venv/bin/python -m autoops sync confluence --dry-run
```

Run fixture connector sync:

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

## Sample Queries

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

```bash
.venv/bin/python -m autoops query "planned maintenance payments settlement replay" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "access request payments runbook space" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "production change checkout cache rollout latency" --db data/autoops.db
```

```bash
.venv/bin/python -m autoops query "PaymentGatewayTimeoutRateHigh legacy timeout" --db data/autoops.db
```

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

outputs/
  Design and acceptance-review deliverables.

tests/
  Unit and fixture tests.

SUBMISSION.md
  Build Week judging notes, demo video script, verification record, and future scope.
```

## Architecture

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

## Data And Safety Model

- Customer PII should not be stored.
- Customer email addresses are blocked.
- Secrets, tokens, API keys, password-like assignments, bearer tokens, and private keys are blocked.
- Sensitive terminal output and real organizational data should not be ingested into this prototype.
- Operational team aliases or internal escalation emails may appear only when directly relevant to ownership or on-call routing.
- Live connector raw payloads default to hash-only storage; sanitized raw snapshots require explicit approval.

## Current Limitations

- No live external connectors are enabled yet.
- Scheduled refresh is implemented as a cron-compatible command, not a long-running daemon.
- No automated ticket or alert triage yet.
- No authentication or authorization on the local prototype API.
- Querying uses SQLite FTS5 and heuristics, not production semantic embeddings.
- Contradiction detection is conservative and rule-based.
- AutoOps flags contradictions but does not decide which source is correct.

## Build Week Notes

This project was built with Codex using GPT-5.6 for the OpenAI Build Week Challenge. 

## License

MIT. See [LICENSE](LICENSE).
