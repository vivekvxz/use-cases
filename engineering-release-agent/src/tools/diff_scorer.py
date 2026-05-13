"""Pure Python diff scorer for heuristic risk analysis."""

from __future__ import annotations

import re


class DiffScorer:
    """Analyse diffs for complexity, churn, and breaking changes."""

    RISK_PATTERNS = [
        r".*/api/.*",
        r".*/auth/.*",
        r".*/payment.*",
        r".*/security.*",
        r".*migration.*",
        r".*schema.*",
        r".*/core/.*",
        r".*config.*",
    ]
    COMPLEXITY_KEYWORDS = [
        "if ",
        "elif ",
        "for ",
        "while ",
        "try:",
        "except",
        "match ",
        "yield",
        "async def",
    ]

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        return "test" in file_path or "spec" in file_path

    @staticmethod
    def _is_file_header(line: str) -> bool:
        return line.startswith("diff --git a/")

    @staticmethod
    def _extract_file_path(line: str) -> str:
        return line.split(" b/")[1] if " b/" in line else ""

    def _compute_scores(
        self,
        additions: int,
        deletions: int,
        complexity_count: int,
        breaking_change_indicators: list[str],
        test_file_additions: int,
        test_file_deletions: int,
    ) -> dict:
        complexity_score = min(complexity_count / 20.0, 1.0)
        churn_score = min((additions + deletions) / 500.0, 1.0)
        test_coverage_delta = min(
            max((test_file_additions - test_file_deletions) / 50.0, -1.0), 1.0
        )
        breaking_change_score = 1.0 if breaking_change_indicators else 0.0
        overall_risk_score = (
            0.4 * complexity_score + 0.3 * churn_score + 0.3 * breaking_change_score
        )
        return {
            "complexity_score": complexity_score,
            "churn_score": churn_score,
            "test_coverage_delta": test_coverage_delta,
            "overall_risk_score": overall_risk_score,
        }

    def _handle_file_header(self, line: str, risk_areas: list[str]) -> str:
        current_file = self._extract_file_path(line)
        for pattern in self.RISK_PATTERNS:
            if re.match(pattern, current_file) and current_file not in risk_areas:
                risk_areas.append(current_file)
        return current_file

    def _handle_added_line(
        self,
        line: str,
        current_file: str,
        complexity_count: int,
        test_file_additions: int,
    ) -> tuple[int, int]:
        for keyword in self.COMPLEXITY_KEYWORDS:
            if keyword in line:
                complexity_count += 1
        if self._is_test_file(current_file):
            test_file_additions += 1
        return complexity_count, test_file_additions

    def _handle_removed_line(
        self,
        line: str,
        current_file: str,
        breaking_change_indicators: list[str],
        test_file_deletions: int,
    ) -> int:
        for pattern in ["def ", "class ", "__init__"]:
            if pattern in line:
                breaking_change_indicators.append(line.strip())
        if self._is_test_file(current_file):
            test_file_deletions += 1
        return test_file_deletions

    def score(self, diff: str) -> dict:
        """Analyse a unified diff and return risk scores.

        Args:
            diff: Unified diff string

        Returns:
            Dict with complexity_score, churn_score, risk_areas, etc.
        """
        if not diff:
            return {
                "complexity_score": 0.0,
                "churn_score": 0.0,
                "risk_areas": [],
                "breaking_change_indicators": [],
                "test_coverage_delta": 0.0,
                "overall_risk_score": 0.0,
            }

        additions = 0
        deletions = 0
        complexity_count = 0
        breaking_change_indicators: list[str] = []
        risk_areas: list[str] = []
        test_file_additions = 0
        test_file_deletions = 0
        current_file = ""

        for line in diff.split("\n"):
            if self._is_file_header(line):
                current_file = self._handle_file_header(line, risk_areas)

            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
                complexity_count, test_file_additions = self._handle_added_line(
                    line, current_file, complexity_count, test_file_additions
                )

            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
                test_file_deletions = self._handle_removed_line(
                    line,
                    current_file,
                    breaking_change_indicators,
                    test_file_deletions,
                )

        scores = self._compute_scores(
            additions,
            deletions,
            complexity_count,
            breaking_change_indicators,
            test_file_additions,
            test_file_deletions,
        )

        return {
            "complexity_score": scores["complexity_score"],
            "churn_score": scores["churn_score"],
            "risk_areas": risk_areas,
            "breaking_change_indicators": breaking_change_indicators,
            "test_coverage_delta": scores["test_coverage_delta"],
            "overall_risk_score": scores["overall_risk_score"],
        }
