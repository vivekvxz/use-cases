# Engineering Release Assistant Agent

A fully local AI agent that analyzes GitHub PRs and produces actionable release feedback.

**Stack:** Python 3.12 · uv · LangGraph · FastAPI · SQLite (local) · ChromaDB (local) · Ollama or OpenAI

**Runs 100% on your laptop.** No cloud infrastructure needed. Swap in cloud services when moving to production.

## Quickstart

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project and add dependencies
mkdir engineering-release-agent && cd engineering-release-agent
uv init --python 3.12
uv add langgraph langchain langchain-openai langchain-community langchain-chroma
uv add fastapi "uvicorn[standard]" httpx
uv add pydantic pydantic-settings
uv add chromadb
uv add sqlalchemy aiosqlite
uv add PyGithub
uv add jira
uv add tiktoken
uv add structlog tenacity
uv add pylint pyflakes
uv add "rich>=13.7" "typer>=0.12"
uv add prometheus-client
uv add --dev pytest pytest-asyncio pytest-cov httpx faker

# Set up environment
cp .env.example .env
# Edit .env — minimum: set GITHUB_TOKEN
# Default mode is local Ollama (USE_OLLAMA=true, OPENAI_ENABLED=false)

# Create local data directories
mkdir -p data/chroma data/hitl data/evals

# Initialize local SQLite database
uv run python -m src.audit.init_db

# Analyze a PR via CLI (quickest path — no API server needed)
uv run python -m src.cli analyze --repo "your-org/your-repo" --pr 42

# OR start the API server
uv run uvicorn src.api.main:app --port 8000
# Swagger UI: http://localhost:8000/docs

# Run evaluation suite
uv run pytest --cov=src --cov-report=term-missing
```

### LLM/Jira Toggle Reference (.env)

Use these switches to explicitly enable or disable integrations:

- `USE_OLLAMA=true` (default): use local Ollama for chat + embeddings.
- `OPENAI_ENABLED=false` (default): disables OpenAI calls entirely.
- `JIRA_ENABLED=false` (default): disables Jira ticket fetching.
- `OLLAMA_EMBED_MODEL=nomic-embed-text` (default): embedding model used for RAG.

To use OpenAI instead of Ollama:

```env
USE_OLLAMA=false
OPENAI_ENABLED=true
OPENAI_API_KEY=sk-...
```

When using Ollama, ensure both chat and embedding models are installed:

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

To enable Jira fetching:

```env
JIRA_ENABLED=true
JIRA_SERVER=https://yourcompany.atlassian.net
JIRA_EMAIL=you@yourcompany.com
JIRA_API_TOKEN=...
```

### Troubleshooting: PR fetch vs model errors

If logs show `diff_fetched_via_pull_files`, PR fetching is working.

If logs show `model "nomic-embed-text" not found`, pull the embedding model:

```bash
ollama pull nomic-embed-text
```

Then restart the API server and retry `POST /analyze`.

## How To Analyze A Specific PR

You can now pass a full GitHub PR URL directly, or use `repo + pr_number`.

### Option A: Pass PR URL directly (recommended)

For your PR `https://github.com/vivekvxz/use-cases/pull/1`:

```bash
uv run python -m src.cli analyze --pr-url "https://github.com/vivekvxz/use-cases/pull/1"
```

### Option B: Pass repo + PR number

```bash
uv run python -m src.cli analyze --repo "vivekvxz/use-cases" --pr 1
```

Both options produce the same review flow. When needed, the app auto-fetches missing PR metadata (base/head SHAs, title, author, changed files) from GitHub API.

### Where PR info is provided in this app

- CLI path (`src/cli.py`): provide either `--pr-url` OR (`--repo` and `--pr`).
- API path (`POST /analyze`): provide either `pr_url` OR (`repo_full_name` + `pr_number`) in JSON.
- Webhook path (`POST /webhook/github`): GitHub sends PR metadata and SHAs automatically.

### API Example (PR URL only)

Start server:

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

Submit an analysis job by PR URL:

```bash
curl -X POST http://localhost:8000/analyze \
    -H "Content-Type: application/json" \
    -d '{
        "pr_url": "https://github.com/vivekvxz/use-cases/pull/1",
        "ticket_ids": ["ENG-123"]
    }'
```

The API returns an `analysis_id`. Poll until complete:

```bash
curl http://localhost:8000/analyze/<analysis_id>
```

Get final Markdown review output:

```bash
curl http://localhost:8000/analyze/<analysis_id>/markdown
```

### API Example (explicit metadata)

Use this when you want full control over every field:

```bash
curl -X POST http://localhost:8000/analyze \
    -H "Content-Type: application/json" \
    -d '{
        "repo_full_name": "vivekvxz/use-cases",
        "pr_number": 1,
        "base_sha": "<base_sha>",
        "head_sha": "<head_sha>",
        "pr_title": "<title>",
        "pr_description": "<description>",
        "ticket_ids": [],
        "author": "<github_user>",
        "changed_files": ["src/api/routes/analyze.py"]
    }'
```

### Swagger Documentation: Full Parameter Reference

Open Swagger UI at `http://localhost:8000/docs`, then expand `POST /analyze`.

Input body fields and behavior:

- `pr_url` (optional, string): Full GitHub PR URL.
    - Example: `https://github.com/vivekvxz/use-cases/pull/1`
    - If provided, repo and PR number are parsed automatically.
- `repo_full_name` (optional, string): `owner/repo` format.
    - Required only when `pr_url` is not provided.
- `pr_number` (optional, integer > 0): pull request number.
    - Required only when `pr_url` is not provided.
- `base_sha` (optional, string): base commit SHA for diff.
    - Auto-fetched from GitHub when omitted.
- `head_sha` (optional, string): head commit SHA for diff.
    - Auto-fetched from GitHub when omitted.
- `pr_title` (optional, string): PR title.
    - Auto-fetched from GitHub when omitted.
- `pr_description` (optional, string): PR body.
    - Auto-fetched from GitHub when omitted.
- `ticket_ids` (optional, array[string]): associated Jira/Linear ticket IDs.
- `author` (optional, string): PR author username.
    - Auto-fetched from GitHub when omitted.
- `changed_files` (optional, array[string]): changed file paths.
    - Auto-fetched from GitHub when omitted or empty.

Validation rules shown in Swagger and enforced by API:

- You must provide either:
    - `pr_url`
    - or both `repo_full_name` and `pr_number`
- `pr_number` must be greater than 0.
- `base_sha` and `head_sha` must be at least 6 characters when provided.

Response fields for `POST /analyze`:

- `analysis_id`: unique ID for polling this job.
- `status`: initial status (`queued`).
- `poll_url`: relative URL to check job status.

For your PR `https://github.com/vivekvxz/use-cases/pull/1`, that means:

- repo: `vivekvxz/use-cases`
- pr: `1`

Run this:

```bash
uv run python -m src.cli analyze --repo "vivekvxz/use-cases" --pr 1
```

### Webhook Flow (no manual PR input)

If you configure GitHub webhooks to call `POST /webhook/github`, the app can auto-enqueue analysis on PR events (`opened`, `synchronize`). In that mode, you do not manually pass repo/PR per request.

## Why Chroma Is Needed

ChromaDB is the local vector database used for retrieval-augmented generation (RAG).

- You ingest architecture docs, runbooks, ADRs, and code notes.
- The app chunks and embeds those documents.
- Chroma stores the embeddings and metadata on disk (`data/chroma`).
- During PR analysis, the agent retrieves semantically relevant chunks and feeds that context to the LLM.

Without Chroma, the agent still runs, but it loses persistent project knowledge and gives weaker, less context-aware feedback.

## Dependency Guide (What Each Package Is For)

### Agent and LLM orchestration

- `langgraph>=0.2`: stateful multi-step workflow graph for agent execution, routing, and checkpoints.
- `langchain>=0.3`: core abstractions (models, prompts, chains, message interfaces).
- `langchain-openai>=0.2`: OpenAI chat and embedding integrations.
- `langchain-community>=0.3`: community integrations, including local model adapters.
- `langchain-chroma>=0.1`: LangChain wrapper around Chroma vector store.

### API and networking

- `fastapi>=0.115`: REST API framework for analysis, review, and webhook endpoints.
- `uvicorn[standard]>=0.30`: ASGI server for running FastAPI with production-ready extras.
- `httpx>=0.27`: async HTTP client used for external API calls and tests.

### Validation and configuration

- `pydantic>=2.8`: typed request/response/state models and validation.
- `pydantic-settings>=2.4`: environment and `.env` based config loading.

### Retrieval and storage

- `chromadb>=0.5`: persistent local vector database for RAG context retrieval.
- `sqlalchemy>=2.0`: ORM/database toolkit for audit log persistence.
- `aiosqlite>=0.20`: async SQLite driver used by SQLAlchemy.

### Source-system integrations

- `PyGithub>=2.3`: GitHub API access (PR metadata, SHAs, repository objects).
- `jira>=3.8`: Jira API client for ticket context enrichment.

### LLM support and reliability

- `tiktoken>=0.7`: token counting/estimation for prompts and usage metrics.
- `structlog>=24.4`: structured logging for traceable agent/API events.
- `tenacity>=8.5`: retry utilities for transient failures.

### Quality tooling and UX

- `pylint>=3.2`: static analysis/linting.
- `pyflakes>=3.2`: lightweight error-focused lint checks.
- `rich>=13.7`: styled terminal output for CLI reports and status panels.
- `typer>=0.12`: ergonomic CLI command definitions.
- `prometheus-client>=0.20`: metrics instrumentation endpoint/counters for observability.

### Dev/test extras

- `pytest>=8.3`: test runner.
- `pytest-asyncio>=0.23`: async test support.
- `pytest-cov>=5.0`: coverage reporting.
- `faker>=26.0`: synthetic test data generation.

## Project Structure

```
engineering-release-agent/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
│
├── data/                           # local runtime data
│   ├── chroma/                     # ChromaDB vector files
│   ├── hitl/                       # pending human-review JSON files
│   ├── release_agent.db            # SQLite audit database
│   └── evals/
│       ├── golden_dataset.json
│       └── reports/
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── models/
│   │   ├── pr_analysis.py
│   │   └── agent_state.py
│   ├── ingestion/
│   │   ├── git_parser.py
│   │   ├── chunker.py
│   │   └── embedder.py
│   ├── tools/
│   │   ├── diff_scorer.py
│   │   ├── jira_fetcher.py
│   │   ├── rag_search.py
│   │   └── code_linter.py
│   ├── agent/
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── prompts.py
│   │   └── hitl.py
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │       ├── analyze.py
│   │       ├── webhook.py
│   │       └── review.py
│   ├── rag/
│   │   ├── pipeline.py
│   │   └── store.py
│   ├── audit/
│   │   ├── logger.py
│   │   └── init_db.py
│   └── evals/
│       └── harness.py
│
└── tests/
    ├── conftest.py
    ├── test_ingestion.py
    ├── test_tools.py
    ├── test_agent.py
    └── test_api.py
```

## Key Features

- **Full PR Analysis** — diff, complexity, security patterns, test coverage
- **Knowledge Base** — ingest your architecture docs into local ChromaDB
- **Human-in-the-Loop** — pause analysis for human review when needed
- **Local or Cloud** — runs on your laptop, swap in cloud services for production
- **Fully Tested** — comprehensive unit tests with 100% coverage
- **Clean Code** — Pylint, Pylance, SonarQube compliant

## Documentation

See the spec file for detailed architecture and implementation guide.
