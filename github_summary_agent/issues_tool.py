"""Tool: read issues for a project via the GitHub REST API.

Uses ``curl`` (via :mod:`github_summary_agent.github_api`) to fetch issues in a
given state (open, closed, or all) and renders them as text the agent can hand
to kiro-cli for the "project direction" and "active community" analysis.

Pull requests are excluded here; they are handled by
:mod:`github_summary_agent.pulls_tool`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .github_api import (  # noqa: F401  (re-exported for backwards compat)
    DEFAULT_API_BASE,
    TOKEN_ENV_VAR,
    GitHubApiError,
    fetch_list,
)


@dataclass(frozen=True)
class Issue:
    """A single issue."""

    number: int
    title: str
    author: str
    created_at: str
    state: str = "open"
    labels: List[str] = field(default_factory=list)
    comments: int = 0


@dataclass(frozen=True)
class IssueCollection:
    """Collected issues for a repository in a particular state."""

    repo: str
    state: str
    issues: List[Issue] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.issues)

    def to_text(self) -> str:
        """Render the issues as plain text for passing to kiro-cli."""
        header = f"{self.state.capitalize()} issues for {self.repo} ({self.count} issues)"
        lines = [header, "=" * len(header), ""]
        for i in self.issues:
            label_str = f" [{', '.join(i.labels)}]" if i.labels else ""
            lines.append(
                f"- #{i.number} | {i.state} | {i.created_at} | by {i.author} | "
                f"{i.comments} comments{label_str} | {i.title}"
            )
        if not self.issues:
            lines.append(f"(no {self.state} issues)")
        return "\n".join(lines)


# Backwards-compatible alias: earlier code referred to ``OpenIssues``.
OpenIssues = IssueCollection


def _parse_issues(data: List[dict], repo: str, state: str) -> IssueCollection:
    issues: List[Issue] = []
    for item in data:
        # The issues endpoint also returns pull requests; skip them.
        if "pull_request" in item:
            continue
        issues.append(
            Issue(
                number=item.get("number", 0),
                title=item.get("title", ""),
                author=(item.get("user") or {}).get("login", "unknown"),
                created_at=item.get("created_at", ""),
                state=item.get("state", state),
                labels=[
                    lbl.get("name", "")
                    for lbl in item.get("labels", [])
                    if isinstance(lbl, dict)
                ],
                comments=item.get("comments", 0),
            )
        )
    return IssueCollection(repo=repo, state=state, issues=issues)


def read_issues(
    repo: str,
    *,
    state: str = "open",
    api_base: str = DEFAULT_API_BASE,
    per_page: int = 100,
    token: str | None = None,
    timeout: float | None = 60,
) -> IssueCollection:
    """Read issues for ``repo`` in the given ``state`` via the GitHub API.

    Args:
        repo: Repository in ``owner/name`` form, e.g. ``"octocat/Hello-World"``.
        state: Issue state to fetch: ``"open"``, ``"closed"``, or ``"all"``.
        api_base: Base URL of the GitHub API.
        per_page: Number of issues to request (max 100 per GitHub).
        token: Optional GitHub token. When ``None``, the ``GITHUB_AUTH_TOKEN``
            environment variable is used if set.
        timeout: Optional command timeout in seconds.

    Returns:
        An :class:`IssueCollection` with the parsed issues (pull requests
        excluded).
    """
    url = f"{api_base}/repos/{repo}/issues?state={state}&per_page={per_page}"
    data = fetch_list(url, repo=repo, token=token, timeout=timeout)
    return _parse_issues(data, repo=repo, state=state)


def read_open_issues(
    repo: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    per_page: int = 100,
    token: str | None = None,
    timeout: float | None = 60,
) -> IssueCollection:
    """Read open issues for ``repo`` (backwards-compatible convenience wrapper)."""
    return read_issues(
        repo,
        state="open",
        api_base=api_base,
        per_page=per_page,
        token=token,
        timeout=timeout,
    )
