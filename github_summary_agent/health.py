"""Deterministic health classification for a repository.

The qualitative memo is produced by kiro-cli, but the fleet roll-up needs a
reliable, testable signal to sort repos into attention buckets. We derive that
signal directly from the collected activity rather than parsing AI prose, so the
roll-up is deterministic and does not require re-reading every memo.

Categories:
- ``healthy``: active and keeping up with incoming work; no management
  attention needed.
- ``attention``: signs that work is piling up or the project has stalled;
  warrants management attention.
- ``investigate``: ambiguous or sparse signals; worth a closer look / keeping
  an eye on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .git_log_tool import GitLog
from .issues_tool import IssueCollection
from .pulls_tool import PullRequestCollection

HEALTHY = "healthy"
ATTENTION = "attention"
INVESTIGATE = "investigate"


@dataclass(frozen=True)
class HealthAssessment:
    """The computed health category for a repo plus a short rationale."""

    repo: str
    category: str
    reason: str


def classify_health(
    repo: str,
    git_log: GitLog,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
) -> HealthAssessment:
    """Classify a repository into a management-attention bucket.

    The rules are intentionally simple and explainable:

    - No commits and no closed work in the window -> ``investigate`` (looks
      dormant or the window/clone may be wrong).
    - A large open backlog relative to what is being closed -> ``attention``.
    - Active commits and healthy close-through -> ``healthy``.
    - Anything else -> ``investigate``.
    """
    commits = git_log.count
    open_work = open_issues.count + open_pulls.count
    closed_work = closed_issues.count + closed_pulls.count

    # Dormant: nothing happened in the window.
    if commits == 0 and closed_work == 0 and open_work == 0:
        return HealthAssessment(
            repo,
            INVESTIGATE,
            "No commits, issues, or pull requests in the window; "
            "repo looks dormant or the time window/clone may be wrong.",
        )

    # Stalled: there is open work but no sign of throughput.
    if commits == 0 and closed_work == 0 and open_work > 0:
        return HealthAssessment(
            repo,
            ATTENTION,
            f"{open_work} open item(s) but no commits and nothing closed in "
            "the window; work appears stalled.",
        )

    # Backlog pressure: open work dwarfs what is being closed.
    if closed_work == 0 and open_work >= 5:
        return HealthAssessment(
            repo,
            ATTENTION,
            f"{open_work} open item(s) with nothing closed in the window.",
        )
    if closed_work > 0 and open_work > 3 * closed_work and open_work >= 10:
        return HealthAssessment(
            repo,
            ATTENTION,
            f"Open work ({open_work}) greatly exceeds closed work "
            f"({closed_work}); backlog is growing.",
        )

    # Active and keeping up.
    if commits > 0 and closed_work >= open_work:
        return HealthAssessment(
            repo,
            HEALTHY,
            f"Active ({commits} commit(s)) and closing at least as much as is "
            f"opened ({closed_work} closed vs {open_work} open).",
        )
    if commits > 0 and closed_work > 0:
        return HealthAssessment(
            repo,
            HEALTHY,
            f"Active ({commits} commit(s)) with ongoing throughput "
            f"({closed_work} closed, {open_work} open).",
        )

    # Everything else is ambiguous.
    return HealthAssessment(
        repo,
        INVESTIGATE,
        f"Mixed signals: {commits} commit(s), {open_work} open, "
        f"{closed_work} closed; worth keeping an eye on.",
    )
