"""Tool: read git logs for a project over a time period.

Produces a structured, text summary of commits that the agent can hand to
kiro-cli. Uses the ``git`` command exclusively, in line with AGENTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .commands import run_command

# Field separator unlikely to appear in commit metadata.
_SEP = "\x1f"
# Record separator between commits.
_REC = "\x1e"

# hash | author name | author email | ISO date | subject
_PRETTY = _SEP.join(["%H", "%an", "%ae", "%aI", "%s"]) + _REC


@dataclass(frozen=True)
class Commit:
    """A single commit parsed from ``git log``."""

    hash: str
    author_name: str
    author_email: str
    date: str
    subject: str


@dataclass(frozen=True)
class GitLog:
    """Collected git log output for a time period."""

    since: str
    until: str | None
    commits: List[Commit] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.commits)

    def to_text(self) -> str:
        """Render the log as plain text for passing to kiro-cli."""
        header = f"Git log since {self.since}"
        if self.until:
            header += f" until {self.until}"
        header += f" ({self.count} commits)"

        lines = [header, "=" * len(header), ""]
        for c in self.commits:
            lines.append(
                f"- {c.date} | {c.author_name} <{c.author_email}> | "
                f"{c.hash[:8]} | {c.subject}"
            )
        if not self.commits:
            lines.append("(no commits in this period)")
        return "\n".join(lines)


def _parse_log(raw: str, since: str, until: str | None) -> GitLog:
    commits: List[Commit] = []
    for record in raw.split(_REC):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_SEP)
        if len(parts) != 5:
            continue
        commits.append(
            Commit(
                hash=parts[0],
                author_name=parts[1],
                author_email=parts[2],
                date=parts[3],
                subject=parts[4],
            )
        )
    return GitLog(since=since, until=until, commits=commits)


def read_git_log(
    repo_path: str,
    *,
    since: str,
    until: str | None = None,
    timeout: float | None = 60,
) -> GitLog:
    """Read git logs for ``repo_path`` over the given time period.

    Args:
        repo_path: Path to a local git repository (clone of the project).
        since: Start of the period, e.g. ``"2026-10-01"`` or ``"2 weeks ago"``.
        until: Optional end of the period.
        timeout: Optional command timeout in seconds.

    Returns:
        A :class:`GitLog` with the parsed commits.
    """
    args = [
        "git",
        "-C",
        repo_path,
        "log",
        f"--since={since}",
        f"--pretty=format:{_PRETTY}",
        "--date=iso-strict",
    ]
    if until is not None:
        args.insert(5, f"--until={until}")

    result = run_command(args, timeout=timeout)
    return _parse_log(result.stdout, since=since, until=until)
