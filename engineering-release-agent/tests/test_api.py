"""Tests for FastAPI routes."""

from __future__ import annotations

import pytest

from src.tools.github_pr import PRDetails


@pytest.mark.asyncio
class TestAPI:
    """Tests for FastAPI routes."""

    async def test_health_check(self, async_client):
        """GET /health returns 200."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_analyze_returns_202(self, async_client, sample_pr_request):
        """POST /analyze returns 202."""
        response = await async_client.post(
            "/analyze",
            json=sample_pr_request.model_dump(),
        )
        assert response.status_code == 202
        data = response.json()
        assert "analysis_id" in data
        assert "status" in data
        assert data["status"] == "queued"

    async def test_analyze_missing_required_field_returns_422(self, async_client):
        """POST /analyze with missing field returns 422."""
        response = await async_client.post("/analyze", json={})
        assert response.status_code == 422

    async def test_analyze_get_unknown_id_returns_404(self, async_client):
        """GET /analyze/unknown-id returns 404."""
        response = await async_client.get("/analyze/does-not-exist-12345")
        assert response.status_code == 404

    async def test_analyze_accepts_pr_url(self, async_client, monkeypatch):
        """POST /analyze accepts pr_url and auto-hydrates metadata."""
        from src.api.routes import analyze as analyze_route

        def mock_fetch_pr_details(_repo, _pr_number, _token):
            return PRDetails(
                repo_full_name="vivekvxz/use-cases",
                pr_number=1,
                base_sha="abcdef1",
                head_sha="1234567",
                title="Test PR",
                description="PR description",
                author="vivekvxz",
                changed_files=["src/cli.py"],
            )

        monkeypatch.setattr(analyze_route, "fetch_pr_details", mock_fetch_pr_details)

        response = await async_client.post(
            "/analyze",
            json={"pr_url": "https://github.com/vivekvxz/use-cases/pull/1"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert "analysis_id" in data

    async def test_webhook_rejects_bad_signature(self, async_client):
        """POST /webhook/github with bad signature returns 401."""
        response = await async_client.post(
            "/webhook/github",
            json={"action": "opened"},
            headers={
                "x-hub-signature-256": "sha256=badhash",
                "x-github-event": "pull_request",
            },
        )
        assert response.status_code == 401

    async def test_webhook_ignores_push_event(self, async_client):
        """POST /webhook/github with push event is skipped."""
        # Create valid signature
        import hmac
        import hashlib
        import json
        from src.config import get_settings

        settings = get_settings()
        body = json.dumps({"action": "opened"}).encode()
        webhook_secret = str(settings.github_webhook_secret)
        sig = (
            "sha256="
            + hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
        )

        response = await async_client.post(
            "/webhook/github",
            content=body,
            headers={
                "x-hub-signature-256": sig,
                "x-github-event": "push",
            },
        )
        assert response.status_code == 200
        assert response.json()["skipped"] is True

    async def test_review_pending_requires_api_key(self, async_client):
        """GET /review/pending without API key returns 422."""
        response = await async_client.get("/review/pending")
        assert response.status_code == 422
