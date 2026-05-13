"""Pytest fixtures and configuration."""

from __future__ import annotations

import pytest
import pytest_asyncio
from faker import Faker
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

from src.models.pr_analysis import (
    DesignFeedback,
    FeedbackType,
    PRAnalysisRequest,
    PRAnalysisResult,
    RiskFlag,
    RiskLevel,
)

fake = Faker()

# Load test environment configuration
load_dotenv(".env.test", override=True)


@pytest.fixture
def sample_pr_request() -> PRAnalysisRequest:
    """Create a sample PR analysis request."""
    return PRAnalysisRequest(
        repo_full_name="acme/payments-service",
        pr_number=42,
        base_sha="abc1234567",
        head_sha="def4567890",
        pr_title="Add retry logic to payment processor",
        pr_description="Adds exponential backoff. Fixes ENG-998.",
        ticket_ids=["ENG-998"],
        author="jane.doe",
        changed_files=["src/payments/gateway.py", "tests/test_gateway.py"],
    )


@pytest.fixture
def sample_risk_flag() -> RiskFlag:
    """Create a sample risk flag."""
    return RiskFlag(
        risk_level=RiskLevel.HIGH,
        feedback_type=FeedbackType.SECURITY,
        title="Missing circuit breaker around external API call",
        description="No circuit breaker at line 42 of gateway.py",
        file_path="src/payments/gateway.py",
        line_range=(40, 55),
        suggested_fix="Wrap with tenacity @circuit or circuitbreaker library",
        confidence=0.88,
        source_citations=["+ response = requests.post(self.url, ...)"],
    )


@pytest.fixture(name="sample_analysis_result")
def fixture_sample_analysis_result(request: pytest.FixtureRequest) -> PRAnalysisResult:
    """Create a sample analysis result."""
    request_fixture = request.getfixturevalue("sample_pr_request")
    risk_flag_fixture = request.getfixturevalue("sample_risk_flag")
    return PRAnalysisResult(
        request=request_fixture,
        risk_flags=[risk_flag_fixture],
        design_feedback=DesignFeedback(
            summary="Solid approach but missing resilience patterns.",
            strengths=["Good test coverage", "Clear variable naming"],
            concerns=["No circuit breaker", "Retry storm possible under load"],
            suggestions=["Add circuit breaker", "Add jitter to backoff"],
        ),
        release_summary="This PR adds retry logic to the payment gateway with exponential backoff.",
        improvement_suggestions=["Consider using tenacity for a unified retry policy"],
        overall_risk_level=RiskLevel.MEDIUM,
        confidence_score=0.82,
        requires_human_review=False,
        agent_iterations=3,
        tokens_used=1_450,
    )


@pytest.fixture
def sample_diff() -> str:
    """Create a sample unified diff."""
    return (
        "diff --git a/src/payments/gateway.py b/src/payments/gateway.py\n"
        "index abc1234..def5678 100644\n"
        "--- a/src/payments/gateway.py\n"
        "+++ b/src/payments/gateway.py\n"
        "@@ -38,6 +38,20 @@ class PaymentGateway:\n"
        "-        response = requests.post(self.url, json={'amount': amount})\n"
        "+        for attempt in range(3):\n"
        "+            try:\n"
        "+                response = requests.post(self.url, json={'amount': amount})\n"
        "+                if response.status_code == 200:\n"
        "+                    return response.json()\n"
        "+            except requests.exceptions.ConnectionError:\n"
        "+                if attempt == 2:\n"
        "+                    raise\n"
        "+                time.sleep(2 ** attempt)\n"
    )


@pytest_asyncio.fixture
async def async_client():
    """Create async test client for FastAPI."""
    from src.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
