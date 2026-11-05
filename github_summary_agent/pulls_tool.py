"""Tool: read pull requests for a project via the GitHub REST API.

Uses ``curl`` (via :mod:`github_summary_agent.github_api`) to fetch pull
requests in a given state (open, closed, or all). PR authorship and review
activity are strong signals of who the active community members are, which the
git log alone does not capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .github_api import DEFAULT_API_BASE, GitHubApiError, fetch_list  # noqa: F401


@dataclass(frozen=True)
class PullRequest:
    """A single pull request."""

    number: int
    title: str
    author: str
    created_at: str
    state: str = "open"
    merged: bool = False


@dataclass(frozen=True)
class PullRequestCollection:
    """Collected pull requests for a repository in a particular state."""

    repo: str
    state: str
    pulls: List[PullRequest] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.pulls)

    def to_text(self) -> str:
        """Render the pull requests as plain text for passing to kiro-cli."""
        header = (
            f"{self.state.capitalize()} pull requests for {self.repo} "
            f"({self.count} PRs)"
        )
        lines = [header, "=" * len(header), ""]
        for p in self.pulls:
            status = p.state
            if p.state == "closed":
                status = "merged" if p.merged else "closed (not merged)"
            lines.append(
                f"- #{p.number} | {status} | {p.created_at} | by {p.author} | "
                f"{p.title}"
            )
        if not self.pulls:
            lines.append(f"(no {self.state} pull requests)")
        return "\n".join(lines)


def _parse_pulls(data: List[dict], repo: str, state: str) -> PullRequestCollection:
    pulls: List[PullRequest] = []
    for item in data:
        pulls.append(
            PullRequest(
                number=item.get("number", 0),
                title=item.get("title", ""),
                author=(item.get("user") or {}).get("login", "unknown"),
                created_at=item.get("created_at", ""),
                state=item.get("state", state),
                # The list endpoint exposes merge state via ``merged_at``.
                merged=bool(item.get("merged_at")),
            )
        )
    return PullRequestCollection(repo=repo, state=state, pulls=pulls)


def read_pull_requests(
    repo: str,
    *,
    state: str = "open",
    api_base: str = DEFAULT_API_BASE,
    per_page: int = 100,
    token: str | None = None,
    timeout: float | None = 60,
) -> PullRequestCollection:
    """Read pull requests for ``repo`` in the given ``state``.

    Args:
        repo: Repository in ``owner/name`` form.
        state: PR state to fetch: ``"open"``, ``"closed"``, or ``"all"``.
            ``"closed"`` includes merged PRs.
        api_base: Base URL of the GitHub API.
        per_page: Number of PRs to request (max 100 per GitHub).
        token: Optional GitHub token. When ``None``, the ``GITHUB_AUTH_TOKEN``
            environment variable is used if set.
        timeout: Optional command timeout in seconds.

    Returns:
        A :class:`PullRequestCollection` with the parsed pull requests.
    """
    url = f"{api_base}/repos/{repo}/pulls?state={state}&per_page={per_page}"
    data = fetch_list(url, repo=repo, token=token, timeout=timeout)
    return _parse_pulls(data, repo=repo, state=state)
