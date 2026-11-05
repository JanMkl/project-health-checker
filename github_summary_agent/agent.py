"""Agent orchestration for the GitHub summary agent.

Two entry points:

- :func:`run_repo` handles a single repository: clone/update it into the working
  directory, fetch its issues and pull requests, decide whether a re-analysis is
  warranted (based on an input fingerprint), run kiro-cli only when needed, and
  write the per-repo memo.
- :func:`run_fleet` runs :func:`run_repo` for every repo in a :class:`Config`
  and writes a single roll-up report classifying repos by how much management
  attention they need.

All writes stay under ``output_dir`` (which defaults under ``output/``), in line
with AGENTS.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from .clone_tool import clone_or_update, repo_slug
from .config import Config
from .fleet import RepoOutcome, build_fleet_report
from .git_log_tool import GitLog, read_git_log
from .health import FAILED, HealthAssessment, classify_health
from .issues_tool import IssueCollection, read_issues
from .memo import generate_memo
from .pulls_tool import PullRequestCollection, read_pull_requests
from .state import (
    compute_fingerprint,
    load_fingerprint,
    save_state,
    state_path,
)

# The only directory tree the agent is permitted to write to (AGENTS.md).
OUTPUT_DIR = "output"


@dataclass(frozen=True)
class RepoResult:
    """Outcome of analysing a single repository."""

    repo: str
    git_log: GitLog
    open_issues: IssueCollection
    closed_issues: IssueCollection
    open_pulls: PullRequestCollection
    closed_pulls: PullRequestCollection
    assessment: HealthAssessment
    memo_markdown: str
    memo_path: str
    analysed: bool  # True if kiro-cli ran this time, False if memo was reused


@dataclass(frozen=True)
class FleetResult:
    """Outcome of a fleet run."""

    results: List[RepoResult]
    report_markdown: str
    report_path: str


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


def run_repo(
    repo: str,
    *,
    since: str,
    until: str | None = None,
    work_dir: str = "output/repos",
    output_dir: str = OUTPUT_DIR,
    token: str | None = None,
    force: bool = False,
) -> RepoResult:
    """Analyse a single repository end-to-end.

    Clones/updates the repo, gathers git log + issues + pull requests, and
    writes a per-repo memo. The kiro-cli analysis is skipped (and the existing
    memo reused) when the input fingerprint matches the stored one, unless
    ``force`` is set.

    Args:
        repo: Repository in ``owner/name`` form.
        since: Start of the git log period.
        until: Optional end of the git log period.
        work_dir: Directory under which repo clones are stored.
        output_dir: Directory to write memos and state into.
        token: Optional GitHub token (falls back to ``GITHUB_AUTH_TOKEN``).
        force: When True, always re-run the analysis even if unchanged.

    Returns:
        A :class:`RepoResult`.
    """
    repo_path = clone_or_update(repo, work_dir)

    git_log = read_git_log(repo_path, since=since, until=until)
    open_issues = read_issues(repo, state="open", token=token)
    closed_issues = read_issues(repo, state="closed", token=token)
    open_pulls = read_pull_requests(repo, state="open", token=token)
    closed_pulls = read_pull_requests(repo, state="closed", token=token)

    assessment = classify_health(
        repo, git_log, open_issues, closed_issues, open_pulls, closed_pulls
    )

    os.makedirs(output_dir, exist_ok=True)
    slug = _slugify(repo)
    memo_path = _resolve_output_path(output_dir, f"{slug}-memo.md")
    st_path = state_path(output_dir, slug)

    fingerprint = compute_fingerprint(
        git_log, open_issues, closed_issues, open_pulls, closed_pulls
    )
    previous = load_fingerprint(st_path)

    # Reuse the existing memo when nothing substantial changed.
    if (
        not force
        and previous is not None
        and previous.digest() == fingerprint.digest()
        and os.path.exists(memo_path)
    ):
        with open(memo_path, encoding="utf-8") as fh:
            memo_markdown = fh.read()
        return RepoResult(
            repo=repo,
            git_log=git_log,
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
            assessment=assessment,
            memo_markdown=memo_markdown,
            memo_path=memo_path,
            analysed=False,
        )

    memo_markdown = generate_memo(
        git_log,
        open_issues=open_issues,
        closed_issues=closed_issues,
        open_pulls=open_pulls,
        closed_pulls=closed_pulls,
    )
    with open(memo_path, "w", encoding="utf-8") as fh:
        fh.write(memo_markdown)
        if not memo_markdown.endswith("\n"):
            fh.write("\n")
    save_state(st_path, fingerprint, memo_path)

    return RepoResult(
        repo=repo,
        git_log=git_log,
        open_issues=open_issues,
        closed_issues=closed_issues,
        open_pulls=open_pulls,
        closed_pulls=closed_pulls,
        assessment=assessment,
        memo_markdown=memo_markdown,
        memo_path=memo_path,
        analysed=True,
    )


def run_fleet(config: Config, *, token: str | None = None, force: bool = False) -> FleetResult:
    """Analyse every repo in ``config`` and write a roll-up report.

    Args:
        config: Parsed multi-repo configuration.
        token: Optional GitHub token (falls back to ``GITHUB_AUTH_TOKEN``).
        force: When True, always re-run analyses even if unchanged.

    Returns:
        A :class:`FleetResult`.
    """
    results: List[RepoResult] = []
    outcomes: List[RepoOutcome] = []
    for repo in config.repos:
        try:
            result = run_repo(
                repo,
                since=config.since,
                until=config.until,
                work_dir=config.work_dir,
                output_dir=config.output_dir,
                token=token,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001 - one bad repo must not abort the fleet
            # Record the failure and continue with the remaining repos.
            outcomes.append(
                RepoOutcome(
                    repo=repo,
                    assessment=HealthAssessment(
                        repo, FAILED, f"Analysis failed: {exc}"
                    ),
                    memo_path="",
                    analysed=False,
                )
            )
            continue

        results.append(result)
        outcomes.append(
            RepoOutcome(
                repo=result.repo,
                assessment=result.assessment,
                memo_path=result.memo_path,
                analysed=result.analysed,
            )
        )

    report_markdown = build_fleet_report(outcomes, output_dir=config.output_dir)

    os.makedirs(config.output_dir, exist_ok=True)
    report_path = _resolve_output_path(config.output_dir, "fleet-report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report_markdown)

    return FleetResult(
        results=results,
        report_markdown=report_markdown,
        report_path=report_path,
    )
