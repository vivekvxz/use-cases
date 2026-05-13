"""GitHub diff parser using PyGithub."""

from __future__ import annotations

import httpx
import structlog
import tiktoken
from github import Github, GithubException
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings

logger = structlog.get_logger(__name__)


class GitDiffParser:
    """Fetch and parse GitHub PRs."""

    MAX_TOKENS = 100_000

    def __init__(self) -> None:
        """Initialize the GitHub API client."""
        settings = get_settings()
        if not settings.github_token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set.\n"
                "1. Go to https://github.com/settings/tokens\n"
                "2. Create a token with 'repo' scope\n"
                "3. Add GITHUB_TOKEN=ghp_... to your .env file"
            )
        self._gh = Github(settings.github_token)
        self._encoder = tiktoken.get_encoding("cl100k_base")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def fetch_diff(
        self, repo_full_name: str, base_sha: str, head_sha: str
    ) -> str:
        """Fetch the unified diff between base_sha and head_sha from GitHub.

        Args:
            repo_full_name: Full repo name e.g. "owner/repo"
            base_sha: Base commit SHA
            head_sha: Head commit SHA

        Returns:
            Raw unified diff string

        Raises:
            ValueError: If diff exceeds MAX_TOKENS
        """
        try:
            repo = self._gh.get_repo(repo_full_name)
            comparison = repo.compare(base_sha, head_sha)

            # Fetch raw diff via httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    comparison.diff_url,
                    headers={"Accept": "application/vnd.github.v3.raw"},
                )
                response.raise_for_status()
                diff = response.text

            # Count tokens
            token_count = len(self._encoder.encode(diff))
            if token_count > self.MAX_TOKENS:
                raise ValueError(
                    f"Diff exceeds MAX_TOKENS ({token_count} > {self.MAX_TOKENS})"
                )

            logger.info(
                "diff_fetched",
                repo=repo_full_name,
                base_sha=base_sha,
                head_sha=head_sha,
                token_count=token_count,
            )
            return diff

        except GithubException as e:
            logger.error("github_error", repo=repo_full_name, error=str(e))
            raise

    def parse_changed_files(self, diff: str) -> list[dict]:
        """Parse a raw unified diff into structured file dicts.

        Args:
            diff: Raw unified diff string

        Returns:
            List of dicts: {file_path, additions, deletions, hunks: [str]}
        """
        files: list[dict] = []
        current_file: str | None = None
        current_hunks: list[str] = []
        current_hunk_lines: list[str] = []

        for line in diff.split("\n"):
            if line.startswith("diff --git a/"):
                self._append_current_file(
                    files, current_file, current_hunks, current_hunk_lines
                )
                current_file = self._extract_file_path(line)
                current_hunks = []
                current_hunk_lines = []
                continue

            if "Binary files" in line:
                current_file = None
                current_hunks = []
                current_hunk_lines = []
                continue

            if line.startswith("@@"):
                if current_hunk_lines:
                    current_hunks.append("\n".join(current_hunk_lines))
                    current_hunk_lines = []
                current_hunk_lines.append(line)
                continue

            if current_hunk_lines and current_file:
                current_hunk_lines.append(line)

        self._append_current_file(
            files, current_file, current_hunks, current_hunk_lines
        )

        for file_info in files:
            additions, deletions = self._count_diff_stats(file_info["hunks"])
            file_info["additions"] = additions
            file_info["deletions"] = deletions

        return files

    @staticmethod
    def _extract_file_path(line: str) -> str | None:
        parts = line.split(" b/")
        if len(parts) >= 2:
            return parts[1]
        return None

    @staticmethod
    def _append_current_file(
        files: list[dict],
        current_file: str | None,
        current_hunks: list[str],
        current_hunk_lines: list[str],
    ) -> None:
        if not current_file:
            return
        hunks = list(current_hunks)
        if current_hunk_lines:
            hunks.append("\n".join(current_hunk_lines))
        files.append(
            {
                "file_path": current_file,
                "additions": 0,
                "deletions": 0,
                "hunks": hunks,
            }
        )

    @staticmethod
    def _count_diff_stats(hunks: list[str]) -> tuple[int, int]:
        additions = 0
        deletions = 0
        for hunk in hunks:
            for line in hunk.split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
        return additions, deletions

    def extract_file_contents(
        self, repo_full_name: str, file_paths: list[str], sha: str
    ) -> dict[str, str]:
        """Fetch raw Python file contents at the given commit SHA.

        Args:
            repo_full_name: Full repo name
            file_paths: List of file paths to fetch
            sha: Commit SHA

        Returns:
            Dict mapping file_path to source code (empty string for non-.py files)
        """
        result = {}
        repo = self._gh.get_repo(repo_full_name)

        for file_path in file_paths:
            try:
                if not file_path.endswith(".py"):
                    result[file_path] = ""
                    continue

                content = repo.get_contents(file_path, ref=sha)
                result[file_path] = content.decoded_content.decode("utf-8")
            except (GithubException, UnicodeDecodeError, AttributeError, OSError):
                result[file_path] = ""

        return result
