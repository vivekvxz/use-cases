"""GitHub PR URL parsing and metadata helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from github import Github


PR_URL_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/.*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PRDetails:
    """Normalized PR details fetched from GitHub API."""

    repo_full_name: str
    pr_number: int
    base_sha: str
    head_sha: str
    title: str
    description: str
    author: str
    changed_files: list[str]


def parse_github_pr_url(pr_url: str) -> tuple[str, int]:
    """Parse a GitHub PR URL into ``(repo_full_name, pr_number)``.

    Args:
        pr_url: Full GitHub pull request URL.

    Returns:
        Tuple containing repo slug and PR number.

    Raises:
        ValueError: If the URL is not a valid GitHub PR URL.
    """
    match = PR_URL_PATTERN.match(pr_url.strip())
    if not match:
        raise ValueError(
            "Invalid PR URL. Expected format: https://github.com/<owner>/<repo>/pull/<number>"
        )

    owner = match.group("owner")
    repo = match.group("repo")
    pr_number = int(match.group("number"))
    return f"{owner}/{repo}", pr_number


def fetch_pr_details(
    repo_full_name: str,
    pr_number: int,
    github_token: str = "",
) -> PRDetails:
    """Fetch pull request metadata from GitHub API.

    Args:
        repo_full_name: Repository slug in ``owner/repo`` format.
        pr_number: Pull request number.
        github_token: Optional GitHub token for authenticated requests.

    Returns:
        PRDetails object.
    """
    client = Github(github_token or None)
    pr_obj = client.get_repo(repo_full_name).get_pull(pr_number)

    return PRDetails(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        base_sha=pr_obj.base.sha,
        head_sha=pr_obj.head.sha,
        title=pr_obj.title or "",
        description=pr_obj.body or "",
        author=pr_obj.user.login,
        changed_files=[file.filename for file in pr_obj.get_files()],
    )