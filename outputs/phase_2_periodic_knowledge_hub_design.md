# Phase 2 Design: AutoOps Periodically Updated Knowledge Hub

## 1. Purpose

Phase 2 upgrades AutoOps from a manually ingested static prototype into a periodically updated knowledge hub. The system should refresh knowledge from approved source systems on a schedule, while preserving the Phase 1 guarantees around citations, freshness, contradiction visibility, sensitive-data protection, and human review.

Phase 2 does not automate triage and does not write back to Jira, PagerDuty, or Slack. It only reads from approved sources and updates the local knowledge index.

## 2. Phase 2 Objective

Implement scheduled read-only ingestion from:

- Confluence pages
- GitLab repository pages/files
- Google Docs discovered through Google Drive
- Jira tickets
- PagerDuty incidents, alerts, and notes
- Slack channel history and thread replies

Refresh cadence should initially support:

- every 8 hours, aligned with on-call shift changes
- manual on-demand rebuild

An 8-hour refresh aligned to on-call shift changes is the scheduled refresh target. Manual refresh remains available for rebuilds, demos, and operational recovery.

## 3. Primary Users And Success Metrics

Primary users:

- on-call engineers who need fast runbook, ticket, alert, and discussion context
- SRE leads who need confidence that the knowledge hub is fresh at shift handoff
- platform owners who maintain runbooks and operational guidance

Top Phase 2 user journeys:

1. An on-call engineer asks about an alert and receives the latest synced runbook plus related historical context.
2. An on-call engineer asks whether a source is stale and sees connector sync time and source update time.
3. An SRE lead checks whether the 8-hour sync completed before shift handoff.
4. A platform owner updates a Confluence runbook and confirms AutoOps reflects the newer version after sync.
5. A connector fails, and query output warns that the related source may be stale.

Phase 2 success metrics:

- 8-hour sync completes successfully for enabled connectors.
- Manual sync can refresh enabled connectors on demand.
- Query results include `last_synced_at`, source update time, and connector status.
- A Confluence runbook update is visible in AutoOps after sync.
- A connector failure is visible in sync status and query freshness warnings.
- Unsafe fixture payloads are blocked before indexing.
- No secrets, customer PII, or sensitive terminal output are stored in raw payload snapshots.
- Golden queries return expected cited sources in automated tests.

## 4. Design Principles

- Keep the Phase 1 normalized retrieval schema.
- Add raw-source metadata storage before mapping into normalized documents.
- Treat every connector as an adapter from source-specific API response shape to AutoOps normalized records.
- Store source version, update time, cursor, and sync metadata.
- Never store secrets, customer PII, sensitive terminal output, or unnecessary organizational data.
- Prefer incremental sync over full rebuild after the first import.
- Make sync failures observable and retryable.
- Do not silently delete old knowledge without retention rules.
- Do not decide which source is correct when conflicts exist.

## 5. Official API Review References

Before implementing each connector, the implementation gate must review the current official API documentation and record the response fields used.

Initial references:

- Confluence Cloud REST API v2 Page endpoints: https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/
- GitLab Repository Files API: https://docs.gitlab.com/api/repository_files/
- GitLab Repository Tree API: https://docs.gitlab.com/api/repositories/
- Google Drive `files.list`: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list
- Google Docs `documents.get`: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get
- Jira Cloud REST API v3 intro and issue shape: https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
- Jira Software issue endpoint: https://developer.atlassian.com/cloud/jira/software/rest/api-group-issue/
- Slack `conversations.history`: https://docs.slack.dev/reference/methods/conversations.history/
- Slack `conversations.replies`: https://docs.slack.dev/reference/methods/conversations.replies/
- PagerDuty API access/authentication background: https://support.pagerduty.com/main/docs/api-access-keys
- PagerDuty public API collection examples for incident notes/alerts: https://www.postman.com/pagerduty/pagerduty-public-api-collection/

PagerDuty note: official response schemas may need to be validated against PagerDuty's current developer API reference or OpenAPI schema before implementation. If the public docs are ambiguous, the connector gate should pause until the exact incident, alert, and note response fields are confirmed.

## 6. Proposed Architecture

```text
scheduled trigger
  -> connector registry
  -> source connector fetches changed records
  -> sensitive-data safety gate
  -> raw source metadata and allowed sanitized payload snapshot stored with sync metadata
  -> source adapter normalizes records
  -> chunking and FTS index refresh
  -> sync audit events
  -> query layer uses updated index
```

## 7. New Storage Concepts

Phase 1 tables should remain:

- `documents`
- `chunks`
- `chunks_fts`
- `audit_events`

Phase 2 should add:

### `source_connections`

Stores connector configuration metadata without secrets.

Suggested fields:

- `connection_id`
- `source_type`
- `display_name`
- `enabled`
- `base_url`
- `scope_description`
- `created_at`
- `updated_at`

Secrets must not be stored in SQLite. API tokens should come from environment variables or a local secret manager.

### `sync_state`

Tracks incremental sync progress per connector.

Suggested fields:

- `connection_id`
- `sync_cursor`
- `last_successful_sync_at`
- `last_attempted_sync_at`
- `last_status`
- `last_error`
- `records_seen`
- `records_changed`

### `raw_source_records`

Stores raw API payload metadata and sanitized payload snapshots only when allowed by the safety policy.

Suggested fields:

- `raw_id`
- `connection_id`
- `source_type`
- `external_id`
- `external_url`
- `external_version`
- `external_created_at`
- `external_updated_at`
- `payload_hash`
- `sanitized_payload_json`
- `payload_storage_mode`
- `ingested_at`
- `deleted_or_archived`

Blocked content must never be stored in raw payload form. If a payload contains secrets, customer PII, sensitive terminal output, or other blocked content, store only audit metadata, source identifiers, payload hash when safe, and the blocking reason. Do not store `sanitized_payload_json` for blocked records.

Recommended default for early Phase 2: store payload hashes plus normalized records only. Enable sanitized raw payload snapshots only for fixture-backed connector tests or after explicit security approval.

### `source_relationships`

Links related artifacts.

Examples:

- PagerDuty incident -> PagerDuty notes
- PagerDuty incident -> Jira ticket
- Jira ticket -> Slack thread
- Jira ticket -> runbook/SOP
- Jira ticket -> access request
- Jira ticket -> production change
- Runbook -> owning service/component
- GitLab file -> commit SHA

Suggested fields:

- `relationship_id`
- `from_source_id`
- `to_source_id`
- `relationship_type`
- `created_at`

## 8. Schema Migration And Idempotency

Phase 2 should introduce explicit schema migrations before adding connector tables.

Recommended migration approach:

- add a `schema_version` table
- keep migration files in a dedicated migrations folder
- make migrations idempotent
- run migrations before sync commands and API startup
- test fresh database creation and migration from the Phase 1 database

Recommended uniqueness constraints:

- `source_connections.connection_id` is unique
- `raw_source_records` should be unique on `connection_id`, `source_type`, `external_id`, and `external_version` where source versions are available
- normalized `documents.source_id` should remain stable across syncs
- chunks for a document should be replaced atomically when the document content changes

Update behavior:

- if payload hash is unchanged, skip re-indexing and record a no-op sync event
- if payload hash changed, replace the normalized document and all chunks for that source
- if a source is archived/deleted, mark it `deleted_or_archived` and exclude it from normal ranking unless explicitly requested
- do not hard-delete source records unless a retention policy requires it

Deduplication rules:

- same external source record should map to one stable AutoOps source ID
- cross-source duplicates should not be merged automatically
- relationships should link related artifacts rather than collapsing them into one record
- source citations must preserve the original source identity

Sync concurrency:

- add a sync lock per connector to prevent overlapping runs
- stale locks should expire after a configurable timeout
- concurrent query reads should continue using the last successful index

## 9. Connector Interface

Each connector should implement the same small interface so source-specific behavior stays isolated.

Suggested interface:

```python
class Connector:
    def validate_connection(self) -> ValidationResult: ...
    def fetch_changes(self, cursor: SyncCursor) -> FetchResult: ...
    def normalize(self, raw_record: RawRecord) -> NormalizedDocument: ...
```

Supporting concepts:

- `ValidationResult`: confirms credentials, scopes, and allowlist access.
- `SyncCursor`: connector-specific cursor state from `sync_state`.
- `FetchResult`: changed records, next cursor, rate-limit metadata, and partial failure details.
- `RawRecord`: source-specific external ID, version, timestamps, URL, payload hash, and optional sanitized payload.
- `NormalizedDocument`: AutoOps document metadata and text content ready for safety checks, chunking, and indexing.

Each connector should also support:

- dry-run mode
- fixture mode
- live mode only after explicit approval
- source allowlist validation
- pagination and rate-limit handling

## 10. Connector Responsibilities

Each connector should:

- authenticate using a least-privilege token
- fetch changed records incrementally where supported
- handle pagination
- handle rate limits and retry-after headers
- normalize timestamps to UTC
- preserve external IDs and URLs
- preserve version/update metadata
- pass content through the safety gate before indexing
- record audit events for success, skip, block, and failure

Each connector should not:

- write to the source system
- store secrets in SQLite
- bypass sensitive-data checks
- silently drop records without audit events

## 11. Platform Account Setup

There is currently no real external data source connected for this project. Before live connector work begins, create or identify the minimum required project-specific accounts and source containers.

Recommended setup order:

1. Create a Confluence account/site and a dedicated AutoOps test space.
2. Add representative runbook/SOP pages in the Confluence test space.
3. Create a least-privilege API token for Confluence read access.
4. Confirm the token can read only the approved test space.
5. Record the allowed space/page IDs in connector configuration.

For later connectors, create or identify:

- GitLab project/repository and approved runbook paths
- Google Drive folder and Google Docs test documents
- Jira project and allowed issue types
- PagerDuty service/escalation policy test data
- Slack workspace/channel test data

Until these exist, connector work should use sanitized fixture payloads and should not assume live API access.

## 12. Source-Specific Notes

### Confluence

Use Confluence page APIs to fetch pages, body content, labels, version metadata, author/owner IDs, and update timestamps.

Official API references reviewed for Gate 4 fixture mapping:

- Confluence Cloud REST API v2 Page group: `https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/`
- Confluence Cloud REST API v2 Version group: `https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-version/`
- Confluence Cloud REST API v2 pagination guidance: `https://developer.atlassian.com/cloud/confluence/rest/v2/intro/`

Gate 4 fixture mapping:

| Confluence API-style field | AutoOps use |
| --- | --- |
| `id` | External page ID; normalized source ID uses `confluence:{id}` |
| `status` | Current pages are indexed; archived/deleted records are recorded and removed from searchable documents |
| `title` | Document title |
| `spaceId` | Fixture allowlist validation |
| `createdAt` | Document creation time |
| `version.number` | Document/source version |
| `version.createdAt` | Document update time and sync cursor candidate |
| `version.authorId` / `authorId` | Author metadata when present |
| `ownerId` | Owner contact metadata when present |
| `body.storage.value` | Source body converted from storage HTML into searchable text |
| `_links.base` + `_links.webui` | Source citation URL |
| `labels` | Tags plus optional `service:`, `component:`, and `alert:` metadata extraction |

Important fields to map:

- page ID
- title
- status
- space ID
- created time
- version number
- version created time
- body representation
- labels
- base/self links

Open questions:

- Which spaces are in scope?
- Should archived pages be indexed as deprecated or excluded?
- Which body representation should be used for clean text extraction?

### GitLab

Use repository tree APIs to discover candidate files and repository file APIs to retrieve content and metadata.

Official API references reviewed for Gate 6 fixture mapping:

- GitLab Repository files API: `https://docs.gitlab.com/api/repository_files/`
- GitLab Repositories API: `https://docs.gitlab.com/api/repositories/`

Gate 6 fixture mapping:

| GitLab API-style field | AutoOps use |
| --- | --- |
| `file_path` | External file ID; normalized source ID uses `gitlab:{file_path}` |
| `file_name` | Document title |
| `ref` | Tag metadata |
| `blob_id` | Raw source metadata reference |
| `commit_id` | Raw source metadata reference |
| `last_commit_id` | Document/source version |
| `content_sha256` | Source content hash reference from upstream |
| `encoding` | Controls content decoding; base64 is decoded before indexing |
| `content` | Searchable runbook body after decoding |
| `size` | Raw source metadata reference |

Important fields to map:

- project ID/path
- file path
- branch/ref
- blob SHA
- commit ID
- last commit ID
- content SHA256
- encoding
- file size

Open questions:

- Which repos and paths contain runbooks?
- Should only default branch be indexed?
- Should merge request discussions be included later?

### Google Docs / Google Drive

Use Drive `files.list` to discover documents by folder, shared drive, modified time, MIME type, and search query. Use Docs `documents.get` to retrieve document structure/content.

Important fields to map:

- file ID
- name
- MIME type
- created time
- modified time
- trashed status
- web view link, if available
- document ID
- document title/body content

Open questions:

- Which folders or shared drives are in scope?
- Should comments/suggestions be included or ignored?
- How should Google Docs structured content be flattened?

### Jira

Use Jira issue APIs to fetch tickets, comments, fields, status, labels, components, links, and update history.

Jira tickets are not assumed to originate from PagerDuty. Some tickets may be linked to PagerDuty incidents, but others may represent access requests, production changes, manually created operational tasks, maintenance follow-ups, or non-alert issues. The Jira connector should ingest Jira issues as first-class sources and create relationships to PagerDuty only when an explicit link, incident ID, alert key, or note reference exists.

Official API references reviewed for Gate 6 fixture mapping:

- Jira Cloud REST API v3 Issues group: `https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/`

Gate 6 fixture mapping:

| Jira API-style field | AutoOps use |
| --- | --- |
| `id` | Raw source metadata reference |
| `key` | External issue ID, ticket ID, and normalized source ID `jira:{key}` |
| `self` | Source citation URL |
| `fields.summary` | Document title and searchable content |
| `fields.description` | Atlassian Document Format text flattened into searchable content |
| `fields.issuetype.name` | Tags and issue classification |
| `fields.status.name` | Tags and lifecycle context |
| `fields.labels` | Tags and service hints |
| `fields.components[].name` | Component metadata |
| `fields.created` | Document creation time |
| `fields.updated` | Document update time, source version, and sync cursor candidate |

Important fields to map:

- issue key
- issue ID
- summary
- status
- labels
- components
- priority
- assignee/reporter
- created/updated timestamps
- description
- comments
- issue links
- custom fields used for service/component/story points

Open questions:

- Which projects and issue types are in scope?
- Which custom fields identify service, component, or on-call routing?
- Should resolved tickets older than a configured window be retained?
- Which issue types should be treated as operational knowledge sources, such as incidents, access requests, production changes, or manually created tickets?

### PagerDuty

Use PagerDuty REST APIs for incidents, alerts, notes, services, escalation policies, and related metadata as needed.

Important fields to map:

- incident ID
- incident number
- title/summary
- status
- urgency/priority
- service
- escalation policy
- created/updated/resolved timestamps
- HTML URL
- alert IDs and alert keys
- notes
- assigned responders

Open questions:

- Which services are in scope?
- Should only triggered/acknowledged incidents be synced, or resolved history too?
- What incident history window should be used?
- Which API fields are available under the chosen account plan and token scopes?

### Slack

Use `conversations.history` for channel messages and `conversations.replies` for threads.

Important fields to map:

- channel ID
- channel name
- message timestamp
- thread timestamp
- user/bot ID
- message text
- permalink, if available later
- edited timestamp
- reply count
- latest reply timestamp

Open questions:

- Which channels are in scope?
- Should bot messages be indexed?
- How should noisy channels be filtered?
- What retention window should be used?
- How should rate limits shape sync cadence?

## 13. Scheduling Strategy

Phase 2 should support two refresh modes:

- every 8 hours, aligned with on-call shift changes
- manual on-demand refresh

Recommended implementation:

- local scheduler command first
- no daemonization initially
- cron-compatible command such as:

```bash
.venv/bin/python -m autoops refresh --connection all --trigger scheduled --db data/autoops.db
```

Gate 5 implementation:

- Manual refresh command: `.venv/bin/python -m autoops refresh --connection all --trigger manual --db data/autoops.db`
- Scheduled refresh command for cron/system schedulers: `.venv/bin/python -m autoops refresh --connection all --trigger scheduled --db data/autoops.db`
- Per-connector lock files under `data/sync_locks` by default.
- API endpoints: `POST /refresh` and `GET /sync/status`.

Later deployment can run this through:

- cron
- systemd timer
- Kubernetes CronJob
- CI scheduled pipeline
- cloud scheduler

The 8-hour scheduled refresh is the default target.

## 14. Incremental Sync Strategy

Each connector should maintain its own cursor strategy:

- timestamp cursor, such as `updated_since`
- page cursor, such as `nextPageToken` or `next_cursor`
- source-specific version cursor, such as Confluence version or GitLab commit SHA

The first sync may be a bounded backfill. Later syncs should fetch only changed records where supported.

If a cursor is rejected or invalid:

- record a sync failure
- do not erase the existing index
- require manual rebuild or connector-specific recovery

## 15. Safety And Compliance Controls

Phase 2 introduces real source data, so safety rules should become stricter than Phase 1.

Required controls:

- token values only from environment variables or a secret manager
- no tokens in logs, SQLite, API responses, or audit messages
- no blocked content in raw payload snapshots, including secrets, customer PII, or sensitive terminal output
- pre-index safety scan
- customer email/PII blocking or redaction based on policy
- terminal output blocking
- audit records for blocked records
- connector allowlists for spaces/repos/projects/channels/services
- optional denylist for known sensitive paths/channels/projects
- local `.env` excluded from git

Data classification:

- `safe`: mock data, public docs, or fixture data with no sensitive values.
- `internal`: operational runbooks, SOPs, service metadata, team aliases, and non-customer incident summaries.
- `sensitive`: internal details that may be indexed only after redaction or explicit approval, such as employee names, internal topology, or non-secret operational details with access restrictions.
- `blocked`: secrets, credentials, customer PII, sensitive terminal output, private keys, tokens, passwords, or content from disallowed sources.

Storage policy by classification:

- `safe`: may be stored and indexed.
- `internal`: may be stored and indexed if source is allowlisted.
- `sensitive`: should be redacted or skipped unless explicitly approved.
- `blocked`: must not be stored in raw payload snapshots, normalized documents, chunks, audit messages, logs, or API responses.

Connector token scope requirements:

- request read-only scopes only
- restrict tokens to approved spaces/repos/folders/projects/services/channels where supported
- do not request write/admin scopes in Phase 2
- document exact scopes per connector before implementation
- validate scopes during connector startup or `/connections/{connection_id}/validate`

Audit-log redaction rules:

- never log token values, request headers, full URLs containing credentials, or raw payload content
- log source identifiers, connector ID, status, error category, and safe counts
- truncate error messages before storage
- redact email addresses unless they are approved operational aliases
- store blocking reason without storing the blocked content

Recommended environment variables:

- `AUTOOPS_CONFLUENCE_TOKEN`
- `AUTOOPS_GITLAB_TOKEN`
- `AUTOOPS_GOOGLE_CREDENTIALS_PATH`
- `AUTOOPS_JIRA_TOKEN`
- `AUTOOPS_PAGERDUTY_TOKEN`
- `AUTOOPS_SLACK_TOKEN`

Credential storage tradeoff:

- Environment variables are simplest for the local prototype and avoid storing secrets in SQLite or source files. They are a good Phase 2 default if `.env` files are excluded from git and logs never print token values.
- A secret manager is safer for shared or deployed environments because it centralizes rotation, access control, and auditability. It adds setup overhead and may not be available while project accounts are still being created.
- Recommendation: use environment variables for local Phase 2 development, then move to a secret manager before shared, team, or production deployment.

Raw payload storage tradeoff:

- Storing sanitized raw payloads helps debugging connector mappings and reprocessing records after schema changes. It increases data exposure risk and requires very strong redaction/blocking guarantees.
- Storing only payload hashes plus normalized records minimizes sensitive-data risk and is easier to reason about. It makes connector debugging harder because original source response details are not available locally.
- Recommendation: default to payload hashes plus normalized records for real data. Allow sanitized raw payload snapshots only for fixture data or after explicit security approval.

## 16. Failure Handling

Connector failures should be isolated. If Slack sync fails, Confluence sync should still complete.

Required failure behavior:

- record failed connector and error category
- preserve last successful index
- retry transient failures with backoff
- honor rate-limit headers
- stop retrying on auth failures until credentials are fixed
- report partial sync status

## 17. Query Impact

The Phase 1 query API should continue to work.

Phase 2 should add query-visible metadata:

- `last_synced_at`
- `source_external_updated_at`
- `source_version`
- `connector_id`
- `sync_status`
- `deleted_or_archived`

Answers should warn when:

- a relevant connector has not synced recently
- a source is stale compared to newer related context
- a source is archived/deprecated
- a connector failed during the latest sync

## 18. Phase 2 API Additions

Implemented local API additions through Gate 5:

- `POST /refresh`
- `GET /sync/status`

Future proposed local API additions:

- `GET /sync/status/{connection_id}`
- `GET /connections`
- `GET /connections/{connection_id}`
- `POST /connections/{connection_id}/validate`

No write-back to external systems is included in Phase 2.

## 19. Test Plan

Phase 2 tests should use recorded/sanitized fixture payloads for each source.

Test categories:

- connector payload parsing
- pagination handling
- cursor persistence
- rate-limit retry behavior
- auth failure handling
- safety blocking before indexing
- raw payload storage policy
- normalized document mapping
- incremental update replacing old content
- archived/deleted source handling
- query freshness warning after connector failure

Fixture matrix:

| Scenario | Expected behavior |
| --- | --- |
| First sync | Creates raw metadata, normalized document, chunks, FTS rows, and sync state |
| Incremental sync with changed record | Updates document and replaces old chunks atomically |
| Incremental sync with unchanged record | Records no-op event and avoids duplicate documents |
| Deleted or archived record | Marks source archived/deleted and changes query ranking |
| Blocked payload | Stores audit metadata only; does not store raw payload snapshot or normalized content |
| Rate limited response | Honors retry metadata and records partial sync status |
| Expired or invalid token | Fails connector validation and preserves existing index |
| Paginated response | Fetches all pages and persists next cursor |
| Malformed response | Records connector error without crashing the entire sync |
| Duplicate external record | Preserves one stable source ID and avoids duplicate chunks |
| Connector failure after partial progress | Keeps last successful index queryable |
| Golden query | Returns expected cited sources after sync |

Golden-query tests:

- Confluence runbook update appears after sync.
- Query warns when Confluence sync failed.
- Query uses manually refreshed data after `POST /sync`.
- Query does not include archived/deleted sources in normal ranking.
- Query still cites original source IDs after cross-source relationship creation.

## 20. Acceptance Criteria

Phase 2 is complete when:

- at least one connector can perform a scheduled incremental sync from fixture-backed source responses
- all connector implementations have documented official API response field mappings
- schema migrations can create a fresh database and migrate a Phase 1 database
- sync state is persisted
- raw source metadata is persisted
- blocked raw payload content is never stored
- unsafe records are blocked before indexing
- unchanged records do not create duplicate documents or chunks
- changed records replace old chunks atomically
- deleted/archived records are represented safely
- connector failures are audited and do not erase existing indexed data
- manual sync command works
- scheduled sync path is documented
- query results include sync/freshness metadata
- at least one golden query returns expected cited sources after fixture sync
- tests pass

Recommended minimum before moving to Phase 3:

- Confluence, GitLab, Google Docs, Jira, PagerDuty, and Slack connector designs are reviewed.
- At least two high-value connectors are implemented and tested end to end.
- One ticket/alert scenario can be answered using periodically refreshed data.
- One connector failure scenario is visible in query output.
- Security review confirms tokens and sensitive data are not stored.

## 21. Current Data Source Assumption

There is currently no real external data source connected for this project. Phase 2 may require creating project-specific trial/developer accounts, workspaces, spaces, repositories, projects, services, or channels before live connector implementation.

Until real accounts exist:

- connector work should use fixture payloads
- allowlists remain TBD
- no live API calls should be assumed
- schema and adapter design should stay source-compatible but account-agnostic

## 22. Implementation Roadmap

Recommended implementation milestones:

1. Platform account setup and Confluence test space.
2. Schema migration foundation.
3. Connector fixture framework.
4. Confluence fixture connector.
5. Confluence live connector.
6. Manual sync command and API endpoint.
7. 8-hour scheduled sync path.
8. Query sync/freshness metadata.
9. Phase 2 acceptance review.

Risk register:

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Platform accounts are not available | Blocks live connector testing | Use fixtures first; create Confluence test space before live work |
| API response shape differs by plan/version | Mapping bugs or missing fields | Record official API mappings and validate against fixture responses |
| Rate limits slow sync | Stale index or partial updates | Honor retry headers, persist cursors, and expose partial sync status |
| Token scopes are too broad | Security exposure | Use read-only least-privilege scopes and validate permissions |
| Blocked content appears in source payload | Sensitive data leakage risk | Run safety gate before storage and never store blocked raw payloads |
| Overlapping sync runs | Duplicate work or inconsistent state | Add per-connector sync locks |
| Connector failure erases useful data | On-call loses context | Preserve last successful index |

## 23. SDLC Approval Gates

Gate 1: Phase 2 design approval

- Review this document.
- Confirm connector priority order.
- Confirm schedule strategy.
- Confirm source allowlists.
- Confirm account setup plan.
- Status: approved.

Gate 2: schema migration approval

- Add raw source, sync state, connection, and relationship tables.
- Add schema versioning and migration runner.
- Add migration tests.
- Status: implemented.

Gate 3: connector fixture approval

- Add sanitized fixture payloads for each source.
- Add fixture matrix tests.
- Do not call live APIs yet.
- Status: implemented.

Gate 4: first connector approval

- Implement one connector end to end against fixture data.
- Recommended first connector: Confluence runbooks.
- Include connector interface, dry-run mode, fixture mode, and live mode guard.
- Status: implemented.

Gate 5: scheduled sync approval

- Implement manual sync command and cron-compatible scheduled sync flow.
- Add per-connector sync locks.
- Status: implemented.

Gate 6: additional connector approval

- Add connectors in priority order.
- Implemented GitLab fixture connector.
- Implemented Jira fixture connector.
- Refresh `all` now runs Confluence, GitLab, and Jira fixture connectors.
- Status: implemented.

Gate 7: Phase 2 acceptance review

- Run test suite.
- Review sync audit behavior.
- Review security classification and blocked-payload evidence.
- Decide whether to proceed to Phase 3.
- Status: implemented.

## 24. Resolved And Open Decisions

Resolved decisions:

1. First live connector: Confluence.
2. Refresh cadence: every 8 hours aligned with on-call shifts, plus manual refresh.
3. Backfill scope: keep all available project-created data initially, because real project accounts and data sources may be created from scratch.
4. Raw payload default: store payload hashes plus normalized records for real data. Store sanitized payload snapshots only for fixtures or after explicit security approval.
5. Credential default: use environment variables for local Phase 2 development, then revisit secret manager support before shared or production deployment.

Current recommended connector priority order:

1. Confluence: highest-value runbooks/SOPs and best first connector.
2. GitLab: runbooks/docs stored with version/commit metadata.
3. Google Drive/Docs: SOPs and ownership docs, often useful but requires document flattening.
4. Jira: historical tickets, manually created operational tasks, access requests, and production changes.
5. PagerDuty: alert/incident history, notes, services, and escalation context.
6. Slack: highly useful context but noisier, rate-limit-sensitive, and requires careful channel allowlisting.

Remaining decisions:

1. Which Confluence spaces/pages are allowed once a real account exists.
2. Which GitLab repos/paths, Google folders, Jira projects/issue types, PagerDuty services, and Slack channels are allowed once accounts exist.
3. Whether project-specific accounts should be created for every platform or only the first connector initially.
4. Whether sanitized raw payload snapshots should ever be enabled for live data after security review.

## 25. Recommended Next Step

Approve Phase 2 Gate 1 after reviewing this document, then choose the first connector and source allowlist.

No Phase 2 implementation should begin until those decisions are confirmed.
