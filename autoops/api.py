from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .connectors import sync_confluence_fixture, sync_gitlab_fixture, sync_jira_fixture
from .ingest import ingest_path
from .query import query_knowledge_hub
from .refresh import refresh_connections
from .storage import connect, get_source, initialize, list_sources, list_sync_states


DEFAULT_DB_PATH = Path("data/autoops.db")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=6, ge=1, le=50)


class IngestRequest(BaseModel):
    source_root: str = "mock_data"
    rebuild: bool = False


class SyncRequest(BaseModel):
    dry_run: bool = False
    fixture_root: str = "connector_fixtures"


class RefreshRequest(BaseModel):
    connection: str = Field(default="all", pattern="^(all|confluence|gitlab|jira)$")
    trigger: str = Field(default="manual", pattern="^(manual|scheduled)$")
    dry_run: bool = False
    fixture_root: str = "connector_fixtures"
    lock_dir: str = "data/sync_locks"


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(
        title="AutoOps API",
        description="Local API for the AutoOps static SRE knowledge hub prototype.",
        version="0.1.0",
    )
    app.state.db_path = db_path

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "autoops", "db_path": str(app.state.db_path)}

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _demo_html()

    @app.get("/demo", response_class=HTMLResponse)
    def demo() -> str:
        return _demo_html()

    @app.post("/ingest")
    def ingest(request: IngestRequest) -> dict[str, Any]:
        summary = ingest_path(Path(request.source_root), app.state.db_path, rebuild=request.rebuild)
        return {
            "db_path": str(summary.db_path),
            "documents_seen": summary.documents_seen,
            "documents_indexed": summary.documents_indexed,
            "documents_blocked": summary.documents_blocked,
            "chunks_indexed": summary.chunks_indexed,
        }

    @app.post("/query")
    def query(request: QueryRequest) -> dict[str, Any]:
        result = query_knowledge_hub(request.query, app.state.db_path, limit=request.limit)
        return result.as_dict()

    @app.post("/sync/confluence")
    def sync_confluence(request: SyncRequest) -> dict[str, Any]:
        result = sync_confluence_fixture(
            app.state.db_path,
            fixture_root=Path(request.fixture_root),
            dry_run=request.dry_run,
        )
        return {
            "connection_id": result.connection_id,
            "source_type": result.source_type,
            "mode": result.mode,
            "dry_run": result.dry_run,
            "records_seen": result.records_seen,
            "records_changed": result.records_changed,
            "documents_indexed": result.documents_indexed,
            "records_archived": result.records_archived,
            "records_blocked": result.records_blocked,
            "status": result.status,
            "message": result.message,
        }

    @app.post("/sync/gitlab")
    def sync_gitlab(request: SyncRequest) -> dict[str, Any]:
        result = sync_gitlab_fixture(
            app.state.db_path,
            fixture_root=Path(request.fixture_root),
            dry_run=request.dry_run,
        )
        return _sync_result_to_dict(result)

    @app.post("/sync/jira")
    def sync_jira(request: SyncRequest) -> dict[str, Any]:
        result = sync_jira_fixture(
            app.state.db_path,
            fixture_root=Path(request.fixture_root),
            dry_run=request.dry_run,
        )
        return _sync_result_to_dict(result)

    @app.post("/refresh")
    def refresh(request: RefreshRequest) -> dict[str, Any]:
        result = refresh_connections(
            app.state.db_path,
            connection=request.connection,
            trigger=request.trigger,
            fixture_root=Path(request.fixture_root),
            lock_dir=Path(request.lock_dir),
            dry_run=request.dry_run,
        )
        return result.as_dict()

    @app.get("/sync/status")
    def sync_status() -> dict[str, Any]:
        conn = connect(app.state.db_path)
        try:
            initialize(conn)
            return {"connections": list_sync_states(conn)}
        finally:
            conn.close()

    @app.get("/sources")
    def sources() -> dict[str, Any]:
        conn = connect(app.state.db_path)
        try:
            initialize(conn)
            return {"sources": list_sources(conn)}
        finally:
            conn.close()

    @app.get("/sources/{source_id}")
    def source_detail(source_id: str) -> dict[str, Any]:
        conn = connect(app.state.db_path)
        try:
            initialize(conn)
            source = get_source(conn, source_id)
        finally:
            conn.close()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
        return source

    @app.get("/openapi-summary")
    def openapi_summary(include_schema: bool = Query(default=False)) -> dict[str, Any]:
        routes = [
            {"method": "GET", "path": "/"},
            {"method": "GET", "path": "/demo"},
            {"method": "GET", "path": "/health"},
            {"method": "POST", "path": "/ingest"},
            {"method": "POST", "path": "/query"},
            {"method": "POST", "path": "/sync/confluence"},
            {"method": "POST", "path": "/sync/gitlab"},
            {"method": "POST", "path": "/sync/jira"},
            {"method": "POST", "path": "/refresh"},
            {"method": "GET", "path": "/sync/status"},
            {"method": "GET", "path": "/sources"},
            {"method": "GET", "path": "/sources/{source_id}"},
        ]
        payload: dict[str, Any] = {"routes": routes}
        if include_schema:
            payload["openapi"] = app.openapi()
        return payload

    return app


def _sync_result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "connection_id": result.connection_id,
        "source_type": result.source_type,
        "mode": result.mode,
        "dry_run": result.dry_run,
        "records_seen": result.records_seen,
        "records_changed": result.records_changed,
        "documents_indexed": result.documents_indexed,
        "records_archived": result.records_archived,
        "records_blocked": result.records_blocked,
        "status": result.status,
        "message": result.message,
    }


def _demo_html() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoOps Demo</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #596573;
      --line: #d7dde5;
      --accent: #116466;
      --accent-strong: #0b4b4d;
      --warn: #9a3412;
      --danger: #991b1b;
      --ok: #166534;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 18px 24px;
    }
    header h1 {
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }
    header p {
      margin: 4px 0 0;
      color: var(--muted);
      max-width: 920px;
    }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      max-width: 1280px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    h2 {
      font-size: 15px;
      margin: 0 0 10px;
      letter-spacing: 0;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 650;
      color: var(--muted);
      margin-bottom: 6px;
    }
    textarea {
      width: 100%;
      min-height: 120px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    button {
      border: 1px solid var(--accent-strong);
      background: var(--accent);
      color: white;
      border-radius: 6px;
      padding: 9px 11px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary {
      background: white;
      color: var(--accent-strong);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .status {
      margin-top: 10px;
      padding: 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      min-height: 40px;
      white-space: pre-wrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .wide { grid-column: 1 / -1; }
    .list {
      display: grid;
      gap: 8px;
    }
    .item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }
    .warning {
      border-color: #fed7aa;
      background: #fff7ed;
      color: var(--warn);
    }
    .danger {
      border-color: #fecaca;
      background: #fef2f2;
      color: var(--danger);
    }
    .ok {
      border-color: #bbf7d0;
      background: #f0fdf4;
      color: var(--ok);
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font-size: 12px;
    }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>AutoOps</h1>
    <p>Timeline-aware SRE knowledge retrieval with citations, contradiction flags, safety screening, and fixture-backed connector sync.</p>
  </header>
  <main>
    <section>
      <h2>Query</h2>
      <label for="query">Alert or ticket context</label>
      <textarea id="query">What should I do for HighKafkaConsumerLag in payments?</textarea>
      <div class="actions">
        <button id="run-query">Run Query</button>
        <button class="secondary" id="ingest">Rebuild Mock Data</button>
        <button class="secondary" id="sync">Refresh All Fixtures</button>
        <button class="secondary" id="sync-status">Sync Status</button>
      </div>
      <div class="status" id="status">Ready</div>
    </section>
    <div class="grid">
      <section class="wide">
        <h2>Answer</h2>
        <div id="answer" class="item">Run a query to populate this view.</div>
      </section>
      <section>
        <h2>Remediation</h2>
        <div id="steps" class="list"></div>
      </section>
      <section>
        <h2>Contradictions</h2>
        <div id="contradictions" class="list"></div>
      </section>
      <section>
        <h2>Sources</h2>
        <div id="sources" class="list"></div>
      </section>
      <section>
        <h2>Timeline</h2>
        <div id="timeline" class="list"></div>
      </section>
      <section class="wide">
        <h2>Raw Response</h2>
        <div class="item"><pre id="raw">{}</pre></div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);

    function setStatus(text) {
      $("status").textContent = text;
    }

    function renderList(id, rows, empty, mapper) {
      const node = $(id);
      node.innerHTML = "";
      if (!rows || rows.length === 0) {
        const item = document.createElement("div");
        item.className = "item ok";
        item.textContent = empty;
        node.appendChild(item);
        return;
      }
      rows.forEach((row) => {
        const item = document.createElement("div");
        item.className = "item";
        item.innerHTML = mapper(row);
        node.appendChild(item);
      });
    }

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[char]);
    }

    async function postJson(path, payload) {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    async function getJson(path) {
      const response = await fetch(path);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    async function runQuery() {
      setStatus("Querying");
      const data = await postJson("/query", {query: $("query").value, limit: 6});
      $("answer").textContent = data.answer;
      $("raw").textContent = JSON.stringify(data, null, 2);
      renderList("steps", data.recommended_remediation_steps, "No source-supported steps found.", (step) =>
        `<strong>${esc(step.step)}</strong><div class="meta">${esc(step.source_ids.join(", "))}</div>`
      );
      renderList("contradictions", data.contradictions, "None detected.", (item) =>
        `<strong>${esc(item.summary)}</strong><div class="meta">${esc(item.source_ids.join(", "))}</div>`
      );
      Array.from($("contradictions").children).forEach((child) => child.classList.add("danger"));
      renderList("sources", data.sources, "No sources returned.", (source) =>
        `<strong>${esc(source.title)}</strong><div class="meta">${esc(source.source_id)} | ${esc(source.source_type)} | updated ${esc(source.updated_at)}</div><div>${esc(source.excerpt)}</div>`
      );
      renderList("timeline", data.timeline_notes, "No timeline notes.", (note) => esc(note));
      setStatus(`Confidence: ${data.confidence}`);
    }

    $("run-query").addEventListener("click", () => runQuery().catch((error) => setStatus(error.message)));
    $("ingest").addEventListener("click", async () => {
      setStatus("Rebuilding mock data");
      const data = await postJson("/ingest", {source_root: "mock_data", rebuild: true});
      setStatus(`Indexed ${data.documents_indexed} documents and ${data.chunks_indexed} chunks`);
      await runQuery();
    });
    $("sync").addEventListener("click", async () => {
      setStatus("Refreshing fixture connectors");
      const data = await postJson("/refresh", {connection: "all", trigger: "manual", dry_run: false});
      const changed = data.items.reduce((total, item) => total + (item.result?.records_changed || 0), 0);
      const indexed = data.items.reduce((total, item) => total + (item.result?.documents_indexed || 0), 0);
      setStatus(`${data.status}: ${changed} changed, ${indexed} indexed`);
      $("query").value = "Kafka consumer lag settlement replay restart";
      await runQuery();
    });
    $("sync-status").addEventListener("click", async () => {
      setStatus("Loading sync status");
      const data = await getJson("/sync/status");
      $("raw").textContent = JSON.stringify(data, null, 2);
      setStatus(`${data.connections.length} connection status record(s)`);
    });
  </script>
</body>
</html>
"""


app = create_app()


def run_server(host: str, port: int, db_path: Path, reload: bool = False) -> None:
    if reload:
        app.state.db_path = db_path
        uvicorn.run("autoops.api:app", host=host, port=port, reload=True)
        return

    uvicorn.run(create_app(db_path), host=host, port=port)


def add_api_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], default_db: Path) -> None:
    api_parser = subparsers.add_parser("serve", help="Run the local AutoOps FastAPI server.")
    api_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    api_parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    api_parser.add_argument("--db", type=Path, default=default_db, help="SQLite database path.")
    api_parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode.")
