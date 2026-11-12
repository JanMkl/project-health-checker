"""Tool: read a project's OWNERS file via the GitHub contents API.

An ``OWNERS`` file lists the project's reviewers and approvers/maintainers —
the people with rights to review and merge pull requests. Its presence is a
positive governance signal: the project is transparent about who holds merge
authority (a convention popularised by the Kubernetes ecosystem). Not every
project uses it, so — like ADOPTERS and SECURITY — we report its presence and
hand the content to the AI memo for the qualitative read.

Unlike ADOPTERS/SECURITY, OWNERS:
- has no ``.md`` extension, and
- is project-specific (per-repo merge permissions), so it lives in the project
  repo rather than the owner's community/.github repos.

We probe the project repo's conventional locations and use the first found:

1. ``<owner>/<name>/OWNERS``
2. ``<owner>/<name>/.github/OWNERS``

Uses ``curl`` (via :mod:`health_checker_agent.github_api`), per AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .github_api import DEFAULT_API_BASE, fetch_text

# Candidate (repo, path) locations to probe, in preference order. OWNERS is
# project-specific, so only the project repo is checked.
_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("{owner}/{name}", "OWNERS"),
    ("{owner}/{name}", ".github/OWNERS"),
)


@dataclass(frozen=True)
class Owners:
    """The OWNERS document found for a repository, if any."""

    repo: str
    # Where it was found, as "owner/repo:path", or None when not found.
    source: Optional[str]
    content: Optional[str]

    @property
    def found(self) -> bool:
        """True when an OWNERS file with content was located.

        Presence is the headline signal (the project publicly documents who may
        review and merge). The content is handed to the AI memo for the
        qualitative read of reviewers/approvers.
        """
        return bool(self.content and self.content.strip())

    def to_text(self) -> str:
        """Render the OWNERS info as plain text for the memo prompt."""
        header = f"Owners for {self.repo}"
        lines = [header, "=" * len(header), ""]
        if not self.found:
            lines.append("(no OWNERS file found)")
            return "\n".join(lines)
        lines.append(f"(source: {self.source})")
        lines.append("")
        lines.append(self.content.strip())
        return "\n".join(lines)


def _candidate_urls(repo: str, api_base: str) -> List[Tuple[str, str]]:
    owner, _, name = repo.partition("/")
    urls: List[Tuple[str, str]] = []
    for repo_tmpl, path in _CANDIDATES:
        full_repo = repo_tmpl.format(owner=owner, name=name)
        source = f"{full_repo}:{path}"
        url = f"{api_base}/repos/{full_repo}/contents/{path}"
        urls.append((source, url))
    return urls


def read_owners(
    repo: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    token: str | None = None,
    timeout: float | None = 60,
) -> Owners:
    """Find and return the OWNERS document for ``repo``.

    Probes the project repo's conventional locations and returns the first one
    found. A missing file is a normal outcome, not an error: ``Owners.found`` is
    then ``False``.

    Args:
        repo: Repository in ``owner/name`` form.
        api_base: Base URL of the GitHub API.
        token: Optional GitHub token (falls back to ``GITHUB_AUTH_TOKEN``).
        timeout: Optional command timeout in seconds.
    """
    for source, url in _candidate_urls(repo, api_base):
        content = fetch_text(url, token=token, timeout=timeout)
        if content and content.strip():
            return Owners(repo=repo, source=source, content=content)
    return Owners(repo=repo, source=None, content=None)
