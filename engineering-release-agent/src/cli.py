"""CLI for the release agent."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from github import Github
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.agent.graph import run_agent
from src.agent.hitl import HITLManager
from src.config import get_settings
from src.evals.harness import EvalHarness
from src.models.pr_analysis import PRAnalysisRequest
from src.rag.pipeline import RAGPipeline

app = typer.Typer(
    name="release-agent",
    help="Engineering Release Assistant Agent",
    add_completion=False,
    pretty_exceptions_enable=False,
)
review_app = typer.Typer(help="Human-in-the-loop review commands")
app.add_typer(review_app, name="review")

console = Console()


@app.command()
def analyze(
    repo: str = typer.Option(..., help="GitHub repo e.g. acme/payments-service"),
    pr: int = typer.Option(..., help="PR number"),
    base: Optional[str] = typer.Option(None, help="Base SHA (auto-fetched if omitted)"),
    head: Optional[str] = typer.Option(None, help="Head SHA (auto-fetched if omitted)"),
    tickets: Optional[str] = typer.Option(None, help="Comma-separated Jira IDs"),
    output: str = typer.Option("console", help="console | markdown | json"),
):
    """Analyse a GitHub pull request and produce a risk report."""
    asyncio.run(_analyze(repo, pr, base, head, tickets, output))


async def _analyze(
    repo: str,
    pr_number: int,
    base: str | None,
    head: str | None,
    tickets: str | None,
    output: str,
) -> None:
    """Async implementation of the analyze command."""
    settings = get_settings()

    # Auto-fetch base/head if not provided
    if not base or not head:
        gh = Github(settings.github_token)
        pr_obj = gh.get_repo(repo).get_pull(pr_number)
        base = base or pr_obj.base.sha
        head = head or pr_obj.head.sha

    # Build request
    request = PRAnalysisRequest(
        repo_full_name=repo,
        pr_number=pr_number,
        base_sha=base,
        head_sha=head,
        pr_title="",
        author="",
        ticket_ids=tickets.split(",") if tickets else [],
    )

    # Run with spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"[cyan]Analysing PR #{pr_number}...", total=None)
        result = await run_agent(request)

    # Output
    if output == "markdown":
        console.print(result.to_markdown())
    elif output == "json":
        import json

        console.print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        console.print(result.to_markdown())


@review_app.command("list")
def review_list():
    """List all pending human review requests."""
    hitl_manager = HITLManager()
    pending = hitl_manager.get_pending()

    if not pending:
        console.print("[green]✅ No pending reviews[/green]")
        return

    table = Table(title="Pending Human Reviews")
    table.add_column("Analysis ID", style="cyan")
    table.add_column("PR Title", style="magenta")
    table.add_column("Risk Level", style="yellow")
    table.add_column("Created At")
    table.add_column("File Path")

    for review in pending:
        table.add_row(
            review["analysis_id"],
            review["pr_title"],
            review["risk_level"],
            review["created_at"],
            review["file_path"],
        )

    console.print(table)


@review_app.command("decide")
def review_decide(
    analysis_id: str = typer.Option(..., help="Analysis ID to decide on"),
    decision: str = typer.Option(..., help="approve | reject | escalate"),
    reviewer: str = typer.Option(..., help="Your name or username"),
    notes: str = typer.Option("", help="Optional reviewer notes"),
):
    """Submit a human decision for a paused analysis."""
    try:
        hitl_manager = HITLManager()
        hitl_manager.submit_decision(analysis_id, decision, reviewer, notes)
        console.print(
            Panel(
                f"[green]✅ Decision recorded[/green]\n"
                f"Analysis: {analysis_id}\n"
                f"Decision: {decision}",
                title="Decision Submitted",
                border_style="green",
            )
        )
    except ValueError as e:
        console.print(f"[red]❌ Error: {e}[/red]")
    except FileNotFoundError:
        console.print(f"[red]❌ Analysis not found: {analysis_id}[/red]")


@app.command()
def ingest(
    file: Optional[str] = typer.Option(None, help="Single file to ingest"),
    dir_path: Optional[str] = typer.Option(
        None, "--dir", help="Directory to ingest recursively"
    ),
    doc_type: str = typer.Option(
        "design_doc", help="design_doc | runbook | architecture_decision"
    ),
):
    """Ingest architecture documents into the local knowledge base."""
    asyncio.run(_ingest(file, dir_path, doc_type))


async def _ingest(file: str | None, dir_path: str | None, doc_type: str) -> None:
    """Async implementation of the ingest command."""
    if not file and not dir_path:
        console.print("[red]Error: provide either --file or --dir[/red]")
        return

    if file and dir_path:
        console.print("[red]Error: provide only one of --file or --dir[/red]")
        return

    pipeline = RAGPipeline()

    if file:
        count = await pipeline.ingest_file(file, doc_type)
        console.print(f"[green]✅ Ingested {count} chunks from {file}[/green]")
    else:
        count = await pipeline.ingest_directory(dir_path, doc_type)
        console.print(f"[green]✅ Ingested {count} chunks from {dir_path}[/green]")


@app.command()
def evaluate(
    dataset: str = typer.Option(
        "data/evals/golden_dataset.json", help="Path to golden dataset JSON"
    ),
):
    """Run the evaluation suite and print a results table."""
    asyncio.run(_evaluate(dataset))


async def _evaluate(dataset_path: str) -> None:
    """Async implementation of the evaluate command."""
    harness = EvalHarness()
    report = await harness.run_suite(dataset_path)
    console.print(
        f"[green]✅ Evaluation complete: {report.pass_rate * 100:.0f}% pass rate[/green]"
    )


if __name__ == "__main__":
    app()
