"""Tests for tool layer."""

from __future__ import annotations

import pytest

from src.tools.code_linter import CodeLinter
from src.tools.diff_scorer import DiffScorer
from src.tools.github_pr import parse_github_pr_url

RISKY_DIFF = (
    "diff --git a/src/auth/middleware.py b/src/auth/middleware.py\n"
    "--- a/src/auth/middleware.py\n"
    "+++ b/src/auth/middleware.py\n"
    "@@ -5,10 +5,3 @@\n"
    "-def validate_jwt(token: str) -> bool:\n"
    "-    if not token:\n"
    "-        return False\n"
    "+    pass\n"
)


class TestDiffScorer:
    """Tests for DiffScorer."""

    def test_score_detects_complexity_keywords(self):
        """Diff with control flow keywords increases complexity_score."""
        scorer = DiffScorer()
        diff = "diff --git a/test.py\n+if condition:\n+    for x in items:\n+        yield x"
        result = scorer.score(diff)
        assert result["complexity_score"] > 0

    def test_score_detects_breaking_change(self):
        """Diff with removed function has breaking_change_indicators."""
        scorer = DiffScorer()
        diff = "diff --git a/test.py\n-def public_api(self):\n-    pass"
        result = scorer.score(diff)
        assert len(result["breaking_change_indicators"]) > 0

    def test_score_detects_risk_areas(self):
        """Diff touching auth files detected in risk_areas."""
        scorer = DiffScorer()
        diff = "diff --git a/src/auth/login.py b/src/auth/login.py\n+# change"
        result = scorer.score(diff)
        # Should detect auth risk
        assert any("auth" in str(area) for area in result["risk_areas"])

    def test_score_all_values_in_range(self):
        """All score values between 0.0 and 1.0."""
        scorer = DiffScorer()
        result = scorer.score(RISKY_DIFF)
        assert 0.0 <= result["complexity_score"] <= 1.0
        assert 0.0 <= result["churn_score"] <= 1.0
        assert 0.0 <= result["overall_risk_score"] <= 1.0

    def test_score_empty_diff_no_crash(self):
        """score('') returns dict with 0.0 values."""
        scorer = DiffScorer()
        result = scorer.score("")
        assert result["complexity_score"] == pytest.approx(0.0)
        assert result["churn_score"] == pytest.approx(0.0)
        assert result["overall_risk_score"] == pytest.approx(0.0)
        assert result["risk_areas"] == []


class TestCodeLinter:
    """Tests for CodeLinter."""

    def test_lint_returns_required_keys(self):
        """lint() returns dict with required keys."""
        linter = CodeLinter()
        result = linter.lint({"test.py": "x = 1"})
        assert "errors" in result
        assert "warnings" in result
        assert "pylint_score" in result
        assert "summary" in result

    def test_lint_skips_non_python(self):
        """lint() skips non-.py files."""
        linter = CodeLinter()
        result = linter.lint({"app.js": "var x = 1"})
        assert result["errors"] == []
        assert result["pylint_score"] == pytest.approx(0.0)

    def test_format_for_prompt_no_results(self):
        """format_for_prompt([]) returns 'No lint issues found.'."""
        linter = CodeLinter()
        result = linter.lint({})
        formatted = linter.format_for_prompt(result)
        assert "No lint issues found" in formatted or "No lint issues" in formatted


class TestGitHubPRTools:
    """Tests for GitHub PR helper utilities."""

    def test_parse_github_pr_url_valid(self):
        """Valid PR URL parses into repo slug and PR number."""
        repo, pr_number = parse_github_pr_url(
            "https://github.com/vivekvxz/use-cases/pull/1"
        )
        assert repo == "vivekvxz/use-cases"
        assert pr_number == 1

    def test_parse_github_pr_url_invalid(self):
        """Invalid URL format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PR URL"):
            parse_github_pr_url("https://github.com/vivekvxz/use-cases/issues/1")
