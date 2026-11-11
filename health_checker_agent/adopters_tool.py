"""Tool: read a project's ADOPTERS file via the GitHub contents API.

Many projects (notably CNCF ones) publish an ``ADOPTERS.md`` listing the
organisations that use the project. By convention this often lives in the org's
central *community* repository rather than in the individual project repo —
e.g. ``metal3-io/community/ADOPTERS.md`` rather than
``metal3-io/metal3-dev-env/ADOPTERS.md``. Knowing a project has notable adopters
is useful management context (it signals real-world importance and support), so
the memo includes it when found.

We look in the most common locations, in order, and use the first one found:

1. the org community repo: ``<owner>/community/ADOPTERS.md``
2. the org ``.github`` repo: ``<owner>/.github/ADOPTERS.md``
3. the project repo itself: ``<owner>/<name>/ADOPTERS.md`` (and ``docs/``)

Uses ``curl`` (via :mod:`health_checker_agent.github_api`), per AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .github_api import DEFAULT_API_BASE, fetch_text

# Candidate (repo, path) locations to probe, in preference order. ``{owner}``
# and ``{name}`` are filled from the analysed repo. The filename casing follows
# the dominant convention (ADOPTERS.md); a couple of common variants are tried.
_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("{owner}/community", "ADOPTERS.md"),
    ("{owner}/community", "adopters.md"),
    ("{owner}/.github", "ADOPTERS.md"),
    ("{owner}/{name}", "ADOPTERS.md"),
    ("{owner}/{name}", "adopters.md"),
    ("{owner}/{name}", "docs/ADOPTERS.md"),
)


@dataclass(frozen=True)
class Adopters:
    """The ADOPTERS document found for a repository, if any."""

    repo: str
    # Where it was found, as "owner/repo:path", or None when not found.
    source: Optional[str]
    content: Optional[str]

    @property
    def found(self) -> bool:
        """True when an ADOPTERS file with content was located.

        We deliberately expose only presence, not a parsed count: ADOPTERS
        files are not standardised (markdown tables, bullet lists, or a stub
        that merely links to an external adopters page), so any count would be
        fragile and sometimes misleading. The qualitative read is left to the
        AI memo, which receives the full content.
        """
        return bool(self.content and self.content.strip())

    def to_text(self) -> str:
        """Render the adopters info as plain text for the memo prompt."""
        header = f"Adopters for {self.repo}"
        lines = [header, "=" * len(header), ""]
        if not self.found:
            lines.append("(no ADOPTERS file found)")
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


def read_adopters(
    repo: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    token: str | None = None,
    timeout: float | None = 60,
) -> Adopters:
    """Find and return the ADOPTERS document for ``repo``.

    Probes the conventional locations (org community repo first, then the
    project repo) and returns the first one found. A missing file is a normal
    outcome, not an error: ``Adopters.found`` is then ``False``.

    Args:
        repo: Repository in ``owner/name`` form.
        api_base: Base URL of the GitHub API.
        token: Optional GitHub token (falls back to ``GITHUB_AUTH_TOKEN``).
        timeout: Optional command timeout in seconds.
    """
    for source, url in _candidate_urls(repo, api_base):
        content = fetch_text(url, token=token, timeout=timeout)
        if content and content.strip():
            return Adopters(repo=repo, source=source, content=content)
    return Adopters(repo=repo, source=None, content=None)
