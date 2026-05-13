"""Evaluation harness with rich table output."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.agent.graph import run_agent
from src.models.pr_analysis import PRAnalysisRequest

console = Console()


class EvalResult(BaseModel):
    """Single evaluation result."""

    example_id: str
    passed: bool
    predicted_risk: str
    expected_risk: str
    false_positives: list[str]
    false_negatives: list[str]
    tokens_used: int
    latency_ms: float


class EvalReport(BaseModel):
    """Evaluation report."""

    run_id: str
    timestamp: datetime
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_latency_ms: float
    avg_tokens: float
    false_positive_rate: float
    false_negative_rate: float
    results: list[EvalResult]


class EvalHarness:
    """Run evaluation suite."""

    @staticmethod
    def _load_json(path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    async def run_suite(
        self, dataset_path: str = "data/evals/golden_dataset.json"
    ) -> EvalReport:
        """Run the full evaluation suite and return a detailed report."""
        # Load dataset
        dataset = await asyncio.to_thread(self._load_json, dataset_path)

        run_id = str(uuid4())
        timestamp = datetime.now(timezone.utc)
        results = []

        # Create progress table
        table = Table(title="Evaluation Progress")
        table.add_column("Example ID", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Predicted", style="yellow")
        table.add_column("Expected")
        table.add_column("FP", style="red")
        table.add_column("FN", style="red")
        table.add_column("Latency (ms)")

        # Run evaluations
        for example in dataset:
            start = time.time()
            try:
                result = await run_agent(PRAnalysisRequest(**example["input"]))
                latency_ms = (time.time() - start) * 1000
                eval_result = self._evaluate_example(
                    result, example["expected"], latency_ms
                )
                results.append(eval_result)

                # Add to table
                status = "✅" if eval_result.passed else "❌"
                fp_count = len(eval_result.false_positives)
                fn_count = len(eval_result.false_negatives)
                table.add_row(
                    eval_result.example_id,
                    status,
                    eval_result.predicted_risk,
                    eval_result.expected_risk,
                    str(fp_count),
                    str(fn_count),
                    f"{latency_ms:.0f}",
                )
            except (KeyError, TypeError, ValueError, RuntimeError) as e:
                console.print(f"[red]Error in {example['example_id']}: {e}[/red]")

        console.print(table)

        # Calculate report
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0
        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0.0
        avg_tokens = sum(r.tokens_used for r in results) / total if total > 0 else 0.0

        false_positives = sum(len(r.false_positives) for r in results)
        false_negatives = sum(len(r.false_negatives) for r in results)
        total_flags = sum(
            len(r.false_positives) + len(r.false_negatives) for r in results
        )
        fp_rate = false_positives / total_flags if total_flags > 0 else 0.0
        fn_rate = false_negatives / total_flags if total_flags > 0 else 0.0

        report = EvalReport(
            run_id=run_id,
            timestamp=timestamp,
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            avg_latency_ms=avg_latency,
            avg_tokens=avg_tokens,
            false_positive_rate=fp_rate,
            false_negative_rate=fn_rate,
            results=results,
        )

        # Save report
        reports_dir = Path("data/evals/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = (
            reports_dir / f"report_{timestamp.isoformat().replace(':', '-')}.json"
        )
        await asyncio.to_thread(
            self._write_json, report_path, report.model_dump(mode="json")
        )

        # Print summary
        console.print(
            Panel(
                f"[bold green]Evaluation Complete[/bold green]\n"
                f"Pass Rate: {pass_rate * 100:.1f}%\n"
                f"Avg Latency: {avg_latency:.0f}ms\n"
                f"Avg Tokens: {avg_tokens:.0f}\n"
                f"Report saved to: {report_path}",
                title="📊 Evaluation Report",
                border_style="green",
            )
        )

        return report

    def _evaluate_example(
        self, result, expected: dict, latency_ms: float
    ) -> EvalResult:
        """Compare agent output to ground truth for one example."""
        raised_types = {f.feedback_type.value for f in result.risk_flags}
        expected_flags = set(expected.get("must_flag", []))
        expected_not_flags = set(expected.get("must_not_flag", []))

        false_positives = [t for t in expected_not_flags if t in raised_types]
        false_negatives = [t for t in expected_flags if t not in raised_types]

        passed = (
            result.overall_risk_level.value == expected.get("risk_level", "")
            and not false_positives
            and not false_negatives
        )

        return EvalResult(
            example_id=expected.get("example_id", "unknown"),
            passed=passed,
            predicted_risk=result.overall_risk_level.value,
            expected_risk=expected.get("risk_level", ""),
            false_positives=false_positives,
            false_negatives=false_negatives,
            tokens_used=result.tokens_used,
            latency_ms=latency_ms,
        )


if __name__ == "__main__":
    harness = EvalHarness()
    asyncio.run(harness.run_suite())
