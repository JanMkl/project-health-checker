"""Tool: read open issues for a project via the GitHub REST API.

Uses ``curl`` exclusively (per AGENTS.md) to fetch open issues and renders them
as text the agent can hand to kiro-cli for the "project direction" analysis.

Note: GitHub serves its issues API from ``api.github.com``. AGENTS.md lists
``github.com`` as the allowed host; the API host is a subdomain of it. The base
URL is configurable so the policy host can be adjusted centrally.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List

from .commands import run_command

DEFAULT_API_BASE = "https://api.github.com"

# Environment variable holding an optional GitHub token. When present, it is
# sent as a Bearer token to raise the API rate limit (5000/hour vs 60/hour).
TOKEN_ENV_VAR = "GITHUB_AUTH_TOKEN"


@dataclass(frozen=True)
class Issue:
    """A single open issue."""

    number: int
    title: str
    author: str
    created_at: str
    labels: List[str] = field(default_factory=list)
    comments: int = 0


@dataclass(frozen=True)
class OpenIssues:
    """Collected open issues for a repository."""

    repo: str
    issues: List[Issue] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.issues)

    def to_text(self) -> str:
        """Render the issues as plain text for passing to kiro-cli."""
        header = f"Open issues for {self.repo} ({self.count} issues)"
        lines = [header, "=" * len(header), ""]
        for i in self.issues:
            label_str = f" [{', '.join(i.labels)}]" if i.labels else ""
            lines.append(
                f"- #{i.number} | {i.created_at} | by {i.author} | "
                f"{i.comments} comments{label_str} | {i.title}"
            )
        if not self.issues:
            lines.append("(no open issues)")
        return "\n".join(lines)


class GitHubApiError(Exception):
    """Raised when the GitHub API returns an error instead of issue data."""


def _parse_issues(raw: str, repo: str) -> OpenIssues:
    data = json.loads(raw) if raw.strip() else []

    # A successful issues response is a JSON array. The API returns a JSON
    # object instead when something goes wrong (e.g. issues disabled, repo not
    # found, rate limited), e.g. {"message": "...", "documentation_url": "..."}.
    if isinstance(data, dict):
        message = data.get("message", "unexpected response from GitHub API")
        raise GitHubApiError(f"GitHub API error for {repo}: {message}")
    if not isinstance(data, list):
        raise GitHubApiError(
            f"GitHub API error for {repo}: expected a list of issues, "
            f"got {type(data).__name__}"
        )

    issues: List[Issue] = []
    for item in data:
        if not isinstance(item, dict):
            # Defensive: skip anything that is not an issue object.
            continue
        # The issues endpoint also returns pull requests; skip them.
        if "pull_request" in item:
            continue
        issues.append(
            Issue(
                number=item.get("number", 0),
                title=item.get("title", ""),
                author=(item.get("user") or {}).get("login", "unknown"),
                created_at=item.get("created_at", ""),
                labels=[
                    lbl.get("name", "")
                    for lbl in item.get("labels", [])
                    if isinstance(lbl, dict)
                ],
                comments=item.get("comments", 0),
            )
        )
    return OpenIssues(repo=repo, issues=issues)


def read_open_issues(
    repo: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    per_page: int = 100,
    token: str | None = None,
    timeout: float | None = 60,
) -> OpenIssues:
    """Read open issues for ``repo`` via the GitHub REST API using curl.

    Args:
        repo: Repository in ``owner/name`` form, e.g. ``"octocat/Hello-World"``.
        api_base: Base URL of the GitHub API.
        per_page: Number of issues to request (max 100 per GitHub).
        token: Optional GitHub token. When ``None``, the value of the
            ``GITHUB_AUTH_TOKEN`` environment variable is used if set. A valid
            token raises the API rate limit.
        timeout: Optional command timeout in seconds.

    Returns:
        An :class:`OpenIssues` with the parsed open issues (pull requests
        excluded).
    """
    url = (
        f"{api_base}/repos/{repo}/issues"
        f"?state=open&per_page={per_page}"
    )
    args = [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        # Follow redirects (e.g. HTTP 301 when a repository has been renamed).
        "--location",
        "--header",
        "Accept: application/vnd.github+json",
    ]

    effective_token = token if token is not None else os.environ.get(TOKEN_ENV_VAR)
    if effective_token:
        args += ["--header", f"Authorization: Bearer {effective_token}"]

    args.append(url)

    result = run_command(args, timeout=timeout)
    return _parse_issues(result.stdout, repo=repo)
