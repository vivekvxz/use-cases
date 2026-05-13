"""Code linter using pylint and pyflakes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile


class CodeLinter:
    """Run pylint and pyflakes on Python files."""

    @staticmethod
    def _build_issue(file_path: str, line: int, message: str, severity: str) -> dict:
        return {
            "file": file_path,
            "line": line,
            "message": message,
            "severity": severity,
        }

    @staticmethod
    def _extract_pylint_score(stderr_text: str) -> float:
        match = re.search(r"Your code has been rated at ([\d.]+)/10", stderr_text)
        if not match:
            return 0.0
        return float(match.group(1))

    @staticmethod
    def _safe_delete(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            return

    def _run_pylint(
        self, file_path: str, tmp_path: str, errors: list[dict], warnings: list[dict]
    ) -> float:
        result = subprocess.run(
            ["python", "-m", "pylint", "--output-format=json", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.stdout:
            try:
                messages = json.loads(result.stdout)
                for msg in messages:
                    severity = msg.get("type", "unknown")
                    issue = self._build_issue(
                        file_path=file_path,
                        line=msg.get("line", 0),
                        message=msg.get("message", ""),
                        severity=severity,
                    )
                    if severity in ("error", "fatal"):
                        errors.append(issue)
                    else:
                        warnings.append(issue)
            except json.JSONDecodeError:
                pass
        return self._extract_pylint_score(result.stderr or "")

    def _run_pyflakes(
        self, file_path: str, tmp_path: str, warnings: list[dict]
    ) -> None:
        result = subprocess.run(
            ["python", "-m", "pyflakes", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if not result.stdout:
            return
        for line in result.stdout.split("\n"):
            if line.strip():
                warnings.append(self._build_issue(file_path, 0, line, "warning"))

    def lint(self, file_contents: dict[str, str]) -> dict:
        """Run pylint and pyflakes on provided Python source files.

        Args:
            file_contents: Dict mapping file paths to source code

        Returns:
            Dict with errors, warnings, pylint_score, summary
        """
        errors: list[dict] = []
        warnings: list[dict] = []
        pylint_score = 0.0

        for file_path, content in file_contents.items():
            if not file_path.endswith(".py"):
                continue

            # Create temporary file
            with tempfile.NamedTemporaryFile(
                suffix=".py", delete=False, mode="w", encoding="utf-8"
            ) as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

            try:
                pylint_score = self._run_pylint(file_path, tmp_path, errors, warnings)
                self._run_pyflakes(file_path, tmp_path, warnings)

            finally:
                self._safe_delete(tmp_path)

        summary = f"{len(errors)} errors, {len(warnings)} warnings across {len(file_contents)} files"

        return {
            "errors": errors,
            "warnings": warnings,
            "pylint_score": pylint_score,
            "summary": summary,
        }

    def format_for_prompt(self, results: dict) -> str:
        """Format lint results as a concise LLM prompt section.

        Args:
            results: Output from lint()

        Returns:
            Formatted string for LLM
        """
        if not results["errors"] and not results["warnings"]:
            return "✅ No lint issues found."

        lines = [f"Pylint Score: {results['pylint_score']:.1f}/10", ""]

        # Show top 5 most severe issues
        all_issues = results["errors"] + results["warnings"]
        for issue in all_issues[:5]:
            lines.append(
                f"- {issue['file']}:{issue['line']} ({issue['severity']}) - {issue['message'][:80]}"
            )

        if len(all_issues) > 5:
            lines.append(f"... and {len(all_issues) - 5} more issues")

        return "\n".join(lines)
