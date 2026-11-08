"""Input fingerprinting and per-repo state persistence.

The agent re-runs the (relatively expensive) kiro-cli analysis only when the
underlying data has changed in a way that could substantially change the memo.
We capture a *fingerprint* of the inputs and persist it alongside the memo. On
a later run, if the fingerprint is unchanged we reuse the existing memo.

The fingerprint deliberately summarises each data source by its size and its
newest item, rather than hashing full contents. Opening or closing an issue or
PR, or landing a new commit, changes the fingerprint; cosmetic churn that does
not change counts or the latest timestamps does not.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass

from .git_log_tool import GitLog
from .issues_tool import IssueCollection
from .pulls_tool import PullRequestCollection


@dataclass(frozen=True)
class Fingerprint:
    """A compact signature of the inputs to a repo's analysis."""

    commit_count: int
    latest_commit: str
    open_issue_count: int
    closed_issue_count: int
    open_pr_count: int
    closed_pr_count: int
    latest_issue_update: str
    latest_pr_update: str

    def digest(self) -> str:
        """Return a short stable hash of this fingerprint."""
        payload = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


def _latest(values: list[str]) -> str:
    """Return the lexicographically greatest value (ISO timestamps sort)."""
    return max(values) if values else ""


def compute_fingerprint(
    git_log: GitLog,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
) -> Fingerprint:
    """Compute a :class:`Fingerprint` from the collected activity."""
    latest_commit = git_log.commits[0].hash if git_log.commits else ""
    issue_dates = [
        i.created_at for i in (*open_issues.issues, *closed_issues.issues)
    ]
    pr_dates = [p.created_at for p in (*open_pulls.pulls, *closed_pulls.pulls)]

    return Fingerprint(
        commit_count=git_log.count,
        latest_commit=latest_commit,
        open_issue_count=open_issues.count,
        closed_issue_count=closed_issues.count,
        open_pr_count=open_pulls.count,
        closed_pr_count=closed_pulls.count,
        latest_issue_update=_latest(issue_dates),
        latest_pr_update=_latest(pr_dates),
    )


def state_path(output_dir: str, slug: str) -> str:
    """Return the path to the per-repo state file."""
    return os.path.join(output_dir, f"{slug}-state.json")


def load_fingerprint(path: str) -> Fingerprint | None:
    """Load a previously stored fingerprint, or ``None`` if absent/unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    try:
        return Fingerprint(**data["fingerprint"])
    except (KeyError, TypeError):
        return None


def save_state(path: str, fingerprint: Fingerprint, memo_path: str) -> None:
    """Persist the fingerprint and the memo path for a repo."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {"fingerprint": asdict(fingerprint), "memo_path": memo_path},
            fh,
            indent=2,
            sort_keys=True,
        )
        fh.write("\n")
