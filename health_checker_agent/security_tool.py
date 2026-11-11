"""Tool: read a project's security policy file via the GitHub contents API.

A ``SECURITY.md`` (or Kubernetes-style ``SECURITY_CONTACTS``) file documents how
the project handles vulnerability disclosure and response. Its mere existence is
a positive governance signal (the project has a documented security process);
its content lets the memo assess whether that process follows responsible-
disclosure best practices (a private reporting channel, response/triage
expectations, embargo handling, etc.).

GitHub recognises ``SECURITY.md`` in the repo root, ``.github/``, and ``docs/``,
and supports an org-level default in the owner's ``.github`` repository. The
Kubernetes ecosystem also uses a ``SECURITY_CONTACTS`` file. We probe these
locations, in order, and use the first one found:

1. the project repo: root, ``.github/``, ``docs/`` (``SECURITY.md``)
2. the project repo: ``SECURITY_CONTACTS`` (Kubernetes convention)
3. the org ``.github`` repo: ``<owner>/.github/SECURITY.md`` (org default)
4. the org community repo: ``<owner>/community`` (``SECURITY.md`` / contacts)

Uses ``curl`` (via :mod:`health_checker_agent.github_api`), per AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .github_api import DEFAULT_API_BASE, fetch_text

# Candidate (repo, path) locations to probe, in preference order. ``{owner}``
# and ``{name}`` are filled from the analysed repo.
_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("{owner}/{name}", "SECURITY.md"),
    ("{owner}/{name}", ".github/SECURITY.md"),
    ("{owner}/{name}", "docs/SECURITY.md"),
    ("{owner}/{name}", "SECURITY_CONTACTS"),
    ("{owner}/{name}", "SECURITY_CONTACTS.md"),
    ("{owner}/.github", "SECURITY.md"),
    ("{owner}/.github", ".github/SECURITY.md"),
    ("{owner}/community", "SECURITY.md"),
    ("{owner}/community", "SECURITY_CONTACTS"),
)


@dataclass(frozen=True)
class SecurityPolicy:
    """The security policy document found for a repository, if any."""

    repo: str
    # Where it was found, as "owner/repo:path", or None when not found.
    source: Optional[str]
    content: Optional[str]

    @property
    def found(self) -> bool:
        """True when a security policy file with content was located.

        Presence is itself the headline signal (the project has a documented
        security disclosure/response process). The content is handed to the AI
        memo, which assesses whether the process follows responsible-disclosure
        best practices.
        """
        return bool(self.content and self.content.strip())

    def to_text(self) -> str:
        """Render the security policy as plain text for the memo prompt."""
        header = f"Security policy for {self.repo}"
        lines = [header, "=" * len(header), ""]
        if not self.found:
            lines.append("(no SECURITY.md or SECURITY_CONTACTS file found)")
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


def read_security_policy(
    repo: str,
    *,
    api_base: str = DEFAULT_API_BASE,
    token: str | None = None,
    timeout: float | None = 60,
) -> SecurityPolicy:
    """Find and return the security policy document for ``repo``.

    Probes the conventional locations (project repo first, then the owner's
    ``.github`` / community repos) and returns the first one found. A missing
    file is a normal outcome, not an error: ``SecurityPolicy.found`` is then
    ``False``.

    Args:
        repo: Repository in ``owner/name`` form.
        api_base: Base URL of the GitHub API.
        token: Optional GitHub token (falls back to ``GITHUB_AUTH_TOKEN``).
        timeout: Optional command timeout in seconds.
    """
    for source, url in _candidate_urls(repo, api_base):
        content = fetch_text(url, token=token, timeout=timeout)
        if content and content.strip():
            return SecurityPolicy(repo=repo, source=source, content=content)
    return SecurityPolicy(repo=repo, source=None, content=None)
