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
# Edit .env — minimum: set GITHUB_TOKEN + OPENAI_API_KEY

# Create local data directories
mkdir -p data/chroma data/hitl data/evals

# Initialize local SQLite database
uv run python -m src.audit.init_db

# Analyze a PR via CLI (quickest path — no API server needed)
uv run python -m src.cli analyze --repo "your-org/your-repo" --pr 42

# OR start the API server
uv run uvicorn src.api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs

# Run evaluation suite
uv run pytest --cov=src --cov-report=term-missing
```

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
