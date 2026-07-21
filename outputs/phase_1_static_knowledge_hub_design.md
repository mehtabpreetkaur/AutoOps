# Phase 1 Design: AutoOps Static SRE Knowledge Hub

## 1. Purpose

On-call engineers currently spend significant time searching across runbooks, SOPs, Jira tickets, PagerDuty alerts, and Slack discussions before they can begin meaningful triage or investigation. Phase 1 will create a local prototype of a static knowledge hub that ingests mock data manually and returns relevant, cited information when queried.

Phase 1 is intentionally limited. It does not integrate with live Confluence, GitLab, Google Docs, Jira, PagerDuty, or Slack. It does not automatically triage tickets or alerts. It does not write back to any external system.

## 2. Phase 1 Objectives

The Phase 1 prototype should:

- Ingest manually provided mock documents.
- Store searchable source content and metadata locally.
- Support CLI-based querying.
- Support API-based querying.
- Return relevant runbooks, SOPs, historical tickets, alerts, and discussion context.
- Read through the relevant retrieved sources and suggest recommended remediation steps based only on those sources.
- Cite every source used in the response.
- Prefer recent information in ranking and timeline notes.
- Flag stale, deprecated, or contradictory information.
- Refuse to invent unsupported answers.
- Warn the user that recommended remediation steps may be incomplete or incorrect and require on-call engineer review.
- Prevent sensitive content from entering the knowledge store.

## 3. Explicit Non-Goals

The following are out of scope for Phase 1:

- Live integrations with Confluence, GitLab, Google Docs, Jira, PagerDuty, or Slack.
- Scheduled ingestion.
- Event-driven triggering from tickets or alerts.
- Automatic Jira ticket updates.
- Automatic PagerDuty note updates.
- Slack posting.
- UI development.
- Autonomous triage.
- External paid services.
- Trust arbitration between contradictory sources.

Contradictions should be flagged only. The system should not decide which source is correct.

## 4. Target Environment

Phase 1 targets a local laptop prototype.

Recommended characteristics:

- Runs locally.
- Uses mock data.
- Uses no-cost dependencies.
- Stores all knowledge locally.
- Can be run from the command line.
- Exposes local API endpoints for future integration work.

## 5. Recommended Stack

Recommended Phase 1 stack:

- Python
- SQLite
- SQLite FTS5 for full-text search
- FastAPI for API endpoints
- Pydantic for request and response schemas
- Typer for CLI
- pytest for tests

Semantic/vector search can be considered later if the keyword and metadata retrieval baseline is insufficient. Phase 1 should start with SQLite FTS5 because many SRE queries include exact terms such as alert names, service names, ticket IDs, components, and runbook titles.

CLI trade-off decision:

- Typer is recommended because it provides a cleaner developer experience, type-hint-driven command definitions, and better help output for a multi-command prototype.
- argparse has the advantage of being built into Python with no extra dependency.
- For AutoOps Phase 1, Typer is the better default because the CLI is expected to grow across ingestion, query, source inspection, audit inspection, and validation commands.

## 6. Data Sources For Prototype

Phase 1 will use mock data only.

Representative mock source categories:

- Confluence runbooks
- GitLab runbooks
- Google Docs SOPs
- Jira ticket history
- PagerDuty alert history
- Slack channel or thread discussions

Suggested mock data folder structure:

```text
mock_data/
  confluence/
  gitlab/
  google_docs/
  jira/
  pagerduty/
  slack/
```

Each mock source should include metadata and content. JSON is recommended as the primary mock source format because it is structured, easy to validate, and works well for metadata-heavy sources such as Jira tickets, PagerDuty alerts, and Slack threads. CSV can be supported later for bulk ticket or alert exports, but it should not be the primary format because nested fields, source metadata, timestamps, thread context, and citations become awkward.

Example:

```json
{
  "source_type": "confluence",
  "source_id": "mock-conf-001",
  "title": "Kafka Consumer Lag Runbook",
  "service": "payments",
  "component": "kafka-consumer",
  "alert_name": "HighKafkaConsumerLag",
  "updated_at": "2026-07-10T12:00:00Z",
  "version": "v3",
  "owner_team": "payments-platform",
  "deprecated": false,
  "content": "# Kafka Consumer Lag Runbook\n\n..."
}
```

## 7. Core Data Model

The prototype should normalize each ingested source into a document record and one or more chunk records.

Document fields:

- `source_id`
- `source_type`
- `source_path`
- `title`
- `service`
- `component`
- `alert_name`
- `ticket_id`
- `incident_id`
- `owner_team`
- `author`
- `created_at`
- `updated_at`
- `version`
- `deprecated`
- `tags`
- `content_hash`
- `ingested_at`

Chunk fields:

- `chunk_id`
- `source_id`
- `chunk_text`
- `chunk_index`
- `source_path`
- `title`
- `source_type`
- `service`
- `component`
- `alert_name`
- `updated_at`
- `version`

Audit event fields:

- `event_id`
- `event_type`
- `source_path`
- `status`
- `message`
- `created_at`

For the prototype, the generated SQLite database should be committed as a generated artifact at `data/autoops.db` after approved ingestion runs. This avoids repeated rebuild effort during reviews and keeps the demo state stable. The source mock data remains the source of truth, and the database should be refreshed manually through an approved rebuild command. A scheduled builder should be deferred to a later phase.

## 8. Sensitive Data Safeguards

Phase 1 must enforce a safety gate before content is stored or indexed.

Content that should not enter the knowledge store:

- PII
- secrets
- access tokens
- API keys
- passwords
- private keys
- terminal outputs containing sensitive values
- real organizational data
- customer email addresses

Operational contact information may be stored when it is directly relevant to escalation or ownership, such as team aliases, on-call team email addresses, escalation team addresses, or support rotation aliases. Customer email addresses should not be stored.

Recommended Phase 1 behavior:

- Block ingestion on high-confidence secret patterns.
- Redact lower-confidence PII-like patterns where practical.
- Record local audit events for blocked or redacted files.
- Make safety checks configurable.
- Treat mock data as safe only after passing the same checks.

Example blocked patterns:

- private key blocks
- `password=...`
- `api_key=...`
- `token=...`
- cloud access key formats
- bearer tokens
- email addresses, if configured as PII
- phone numbers, if configured as PII

## 9. Ingestion Flow

Manual ingestion flow:

```text
mock source files
  -> read metadata and content
  -> run sensitive-data safety checks
  -> normalize metadata
  -> chunk content
  -> store documents in SQLite
  -> store chunks in SQLite
  -> index chunks in SQLite FTS5
  -> record audit events
```

Proposed CLI command:

```bash
python -m autoops ingest mock_data/
```

## 10. Query Flow

Query flow:

```text
user query
  -> normalize query
  -> run FTS5 search
  -> apply metadata-aware ranking
  -> collect candidate chunks
  -> group by source
  -> identify most recent related sources
  -> detect stale or deprecated sources
  -> flag contradictions
  -> derive recommended remediation steps from cited sources
  -> produce cited response
```

Proposed CLI command:

```bash
python -m autoops query "What should I do for HighKafkaConsumerLag in payments?"
```

## 11. API Contract

Initial local API endpoints:

```text
GET  /health
POST /ingest
POST /query
GET  /sources
GET  /sources/{source_id}
```

Example query request:

```json
{
  "query": "What should I do for HighKafkaConsumerLag in payments?",
  "filters": {
    "service": "payments",
    "alert_name": "HighKafkaConsumerLag"
  }
}
```

Example query response:

```json
{
  "answer": "The most relevant runbook is Kafka Consumer Lag Runbook v3. Review broker health before restarting the consumer group.",
  "recommended_remediation_steps": [
    {
      "step": "Check broker health before restarting the consumer group.",
      "source_ids": ["mock-conf-001"]
    },
    {
      "step": "Review the newer Slack thread for the temporary mitigation before applying the standard restart workflow.",
      "source_ids": ["mock-slack-001"]
    }
  ],
  "remediation_warning": "These remediation steps are generated from retrieved knowledge hub sources and may be incomplete or incorrect. The on-call engineer must verify them before taking action.",
  "sources": [
    {
      "source_id": "mock-conf-001",
      "title": "Kafka Consumer Lag Runbook",
      "source_type": "confluence",
      "source_path": "mock_data/confluence/kafka_consumer_lag.json",
      "updated_at": "2026-07-10T12:00:00Z",
      "version": "v3"
    }
  ],
  "timeline_notes": [
    "A Slack thread updated on 2026-07-12 is newer than the Confluence runbook and mentions a temporary mitigation."
  ],
  "contradictions": [
    {
      "summary": "Restart guidance differs between Confluence and GitLab runbooks.",
      "sources": ["mock-conf-001", "mock-gitlab-001"]
    }
  ],
  "gaps": [
    "No PagerDuty history found for this exact alert name."
  ],
  "confidence": "medium"
}
```

## 12. Response Format

Every human-readable answer should include:

- Direct answer
- Recommended remediation steps derived only from cited sources
- Warning that remediation steps may be incomplete or incorrect and require engineer review
- Relevant runbook or SOP
- Historical Jira or PagerDuty context
- Relevant Slack or discussion context
- Timeline and freshness notes
- Contradictions or deviations
- Gaps or missing evidence
- Citations
- Confidence level

The system should not provide unsupported operational instructions. If evidence is insufficient, the answer should say so clearly.

Recommended remediation steps must be traceable to cited source chunks. If no retrieved source supports a remediation step, that step must not be included.

## 13. Ranking Rules

Initial ranking signals:

- Exact alert name match
- Exact service or component match
- Exact ticket or incident ID match
- Keyword relevance from FTS5
- Recent `updated_at`
- Deprecated status
- Source type match

Freshness should influence ranking and timeline notes, but it should not silently suppress older sources. Older sources may still be relevant, especially when they contradict newer information.

## 14. Contradiction Detection

Phase 1 contradiction detection should be conservative and explainable.

Initial contradiction patterns:

- Different recommended action for the same alert and service.
- Conflicting restart guidance, such as "restart immediately" vs "do not restart".
- Conflicting escalation owner for the same service.
- Conflicting threshold values for the same alert.
- Deprecated source conflicts with active source.
- Slack discussion describes a temporary workaround that differs from a runbook.

The output should flag contradictions for human review. It should not decide the correct source.

Contradiction patterns should start as code-level constants for Phase 1 to avoid premature configuration complexity. A YAML or JSON configuration file can be introduced later if the patterns change frequently during testing or need to be maintained by non-developers.

## 15. Testing Strategy

Focused tests should cover:

- Ingestion of valid mock documents.
- Rejection of documents containing high-confidence secrets.
- Redaction or flagging of configured PII patterns.
- Correct indexing into SQLite FTS5.
- Query results include citations.
- Query results include remediation steps only when supported by cited sources.
- Query results include a warning that remediation steps may be incomplete or incorrect.
- Query results prefer direct alert and service matches.
- Query results surface newer related sources in timeline notes.
- Deprecated sources are marked.
- Seeded contradictions are detected.
- Missing evidence is reported as a gap.
- API and CLI return consistent results.

## 16. Phase 1 Acceptance Criteria

Phase 1 is complete when:

- Mock data can be ingested manually.
- Local searchable index is created.
- CLI query returns cited results.
- API query returns equivalent structured results.
- Responses include source citations.
- Responses include recommended remediation steps when supported by cited sources.
- Responses include a visible remediation warning.
- Responses include freshness or timeline notes.
- Seeded contradictions are flagged.
- Sensitive data checks run before storage.
- Tests pass.
- The system avoids unsupported claims.

Suggested quality bar before moving to Phase 2:

- Correct runbook appears in top results for seeded test alerts.
- Relevant historical mock tickets or alerts are retrieved for seeded scenarios.
- Newer related context is visibly surfaced.
- Contradictions are flagged without deciding truth.
- No answer is produced without at least one citation, unless the answer is explicitly "insufficient evidence".
- No remediation step is produced without citation support.

## 17. SDLC Approval Gates

All implementation should proceed through explicit approval gates.

Gate 1: Design approval

- Review this design document.
- Confirm Phase 1 scope and constraints.
- Approve prototype scaffold only after design is accepted.

Gate 2: Prototype scaffold approval

- Create project structure.
- Create mock data folder layout.
- Create README.
- No ingestion/query logic yet unless separately approved.

Gate 3: Ingestion MVP approval

- Implement local ingestion.
- Implement sensitive-data safety checks.
- Implement SQLite schema and FTS5 index.

Gate 4: Query MVP approval

- Implement CLI query.
- Return citations, timeline notes, gaps, and confidence.

Gate 5: API MVP approval

- Implement FastAPI endpoints.

Gate 6: Contradiction and freshness approval

- Implement conservative contradiction detection.
- Implement stale/deprecated source warnings.

Gate 7: Test and phase review approval

- Add tests.
- Run acceptance checks.
- Decide whether Phase 1 is complete.

## 18. Open Questions

Resolved decisions:

1. The project name is `AutoOps`.
2. CLI decision: use Typer unless dependency constraints later require argparse.
3. Mock source format: use JSON as the primary format. Consider CSV later for simple bulk exports only.
4. Email handling: allow operational team or escalation email addresses when directly relevant to ownership or on-call routing. Do not store customer email addresses.
5. SQLite database handling: commit the local SQLite database as a generated artifact at `data/autoops.db` for the prototype so reviewers do not need to rebuild every time.
6. Contradiction configuration: start with code-level constants. Revisit YAML or JSON configuration after Phase 1 testing shows whether the patterns need frequent tuning.
7. Database refresh handling: refresh the generated database manually through an approved command during Phase 1. Scheduled rebuilds are deferred to a later phase.

## 19. Recommended Next Step

Recommended next approval request:

Approve Gate 2, prototype scaffold creation.

That would create the folder structure, README, and representative mock data files only. It would not implement ingestion, querying, API endpoints, or tests until later approval gates.
