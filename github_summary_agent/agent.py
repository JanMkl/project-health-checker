"""Agent orchestration for the GitHub summary agent.

Ties the tools together:
1. Read git logs for a period (git_log_tool).
2. Read open issues (issues_tool).
3. Ask kiro-cli to write a management memo (memo).
4. Write the memo to the ``output/`` directory (the only writable location per
   AGENTS.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .git_log_tool import GitLog, read_git_log
from .issues_tool import OpenIssues, read_open_issues
from .memo import generate_memo

# The only directory the agent is permitted to write to (AGENTS.md).
OUTPUT_DIR = "output"


@dataclass(frozen=True)
class SummaryResult:
    """Outcome of a summary run."""

    repo: str
    git_log: GitLog
    issues: OpenIssues
    memo_markdown: str
    memo_path: str


def _slugify(repo: str) -> str:
    """Turn ``owner/name`` into a filesystem-safe slug."""
    return repo.replace("/", "__").replace(" ", "_")


def _resolve_output_path(output_dir: str, filename: str) -> str:
    """Resolve a path inside ``output_dir`` and guard against escaping it."""
    base = os.path.abspath(output_dir)
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError(
            f"Refusing to write outside the output directory: {filename!r}"
        )
    return target


def summarise_project(
    repo: str,
    repo_path: str,
    *,
    since: str,
    until: str | None = None,
    output_dir: str = OUTPUT_DIR,
    token: str | None = None,
) -> SummaryResult:
    """Run the full summary pipeline for a single project.

    Args:
        repo: Repository in ``owner/name`` form (used for the issues API and
            output filename).
        repo_path: Path to the local clone of the repository.
        since: Start of the git log period.
        until: Optional end of the git log period.
        output_dir: Directory to write the memo into. Defaults to ``output``.
        token: Optional GitHub token for the issues API. When ``None``, the
            ``GITHUB_AUTH_TOKEN`` environment variable is used if set.

    Returns:
        A :class:`SummaryResult` including the written memo path.
    """
    git_log = read_git_log(repo_path, since=since, until=until)
    issues = read_open_issues(repo, token=token)
    memo_markdown = generate_memo(git_log, issues)

    os.makedirs(output_dir, exist_ok=True)
    filename = f"{_slugify(repo)}-memo.md"
    memo_path = _resolve_output_path(output_dir, filename)
    with open(memo_path, "w", encoding="utf-8") as fh:
        fh.write(memo_markdown)
        if not memo_markdown.endswith("\n"):
            fh.write("\n")

    return SummaryResult(
        repo=repo,
        git_log=git_log,
        issues=issues,
        memo_markdown=memo_markdown,
        memo_path=memo_path,
    )
