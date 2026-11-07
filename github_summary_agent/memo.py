"""Generate a management memo via kiro-cli.

Builds a prompt from the git log, issues (open + closed), and pull requests
(open + closed), then asks ``kiro-cli`` to write a markdown management memo
analysing project direction, active contributors, and project health.
"""

from __future__ import annotations

from .commands import run_command
from .git_log_tool import GitLog
from .issues_tool import IssueCollection
from .pulls_tool import PullRequestCollection

_PROMPT_TEMPLATE = """\
You are a technical program manager. Using the project activity below, write a \
management memo in GitHub-flavoured Markdown.

The memo MUST use these sections, with these exact Markdown headings, in this \
order:
- A top-level heading (the project name).
- "## Executive Summary" — a short, self-contained paragraph suitable for a \
non-technical leadership audience.
- "## Project Direction" — analyse the DIRECTION of the project (what themes \
the recent commits, issues, and pull requests point toward). Present the themes \
as a bulleted list, then end this section with exactly ONE sentence summarising \
the overall project direction, on its own line, prefixed verbatim with \
"**Direction summary:**" (for example: "**Direction summary:** The project is \
in a maturity-focused phase, prioritising stability and security over new \
features."). This one-sentence summary is REQUIRED and must appear after the \
bulleted list.
- "## Active Contributors and Community Members" — identify the active \
contributors and community members. Do NOT rely on commit authorship alone; \
many active members contribute mainly by opening and resolving issues and by \
authoring and reviewing pull requests. Cross-reference commit authors with \
issue and pull-request authors to find who is genuinely active, and call out \
community members who are active in issues/PRs even if they have few or no \
commits.
- "## Project Health" — assess the health of the project (activity level, how \
open work compares to what is being closed/merged, and responsiveness).
- "## Risks" — a bulleted list of the key risks warranting management \
attention. Each bullet should be a brief, self-contained risk statement.
- A final closing line, on its own, prefixed verbatim with \
"**Overall assessment:**" followed by exactly ONE sentence giving the overall \
bottom-line judgement of the project (for example: "**Overall assessment:** A \
well-run, actively maintained project whose main management action is reducing \
reliance on its lead maintainer."). This one-sentence assessment is REQUIRED \
and must be the last line of the memo.

Be concise and suitable for a non-technical leadership audience. Output \
Markdown only, with no surrounding commentary.

## Git activity
{git_log}

## Open issues
{open_issues}

## Closed issues
{closed_issues}

## Open pull requests
{open_pulls}

## Closed pull requests
{closed_pulls}
"""


def build_prompt(
    git_log: GitLog,
    *,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
) -> str:
    """Build the kiro-cli prompt from the collected activity."""
    return _PROMPT_TEMPLATE.format(
        git_log=git_log.to_text(),
        open_issues=open_issues.to_text(),
        closed_issues=closed_issues.to_text(),
        open_pulls=open_pulls.to_text(),
        closed_pulls=closed_pulls.to_text(),
    )


def generate_memo(
    git_log: GitLog,
    *,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
    timeout: float | None = 300,
) -> str:
    """Ask kiro-cli to produce a markdown management memo.

    Args:
        git_log: Collected git log for the period.
        open_issues: Open issues.
        closed_issues: Closed issues.
        open_pulls: Open pull requests.
        closed_pulls: Closed pull requests.
        timeout: Optional command timeout in seconds.

    Returns:
        The memo as a Markdown string.
    """
    prompt = build_prompt(
        git_log,
        open_issues=open_issues,
        closed_issues=closed_issues,
        open_pulls=open_pulls,
        closed_pulls=closed_pulls,
    )
    # Feed the prompt on stdin rather than as a command-line argument. Prompts
    # for large repositories can exceed the OS argument-length limit (ARG_MAX),
    # which raises "OSError: [Errno 7] Argument list too long". `kiro-cli chat`
    # reads the prompt from stdin when no positional INPUT is given.
    # `--no-interactive` runs without expecting further input and
    # `--trust-all-tools` avoids blocking on tool-permission prompts.
    args = [
        "kiro-cli",
        "chat",
        "--no-interactive",
        "--trust-all-tools",
    ]
    result = run_command(args, timeout=timeout, stdin_input=prompt)
    return result.stdout.strip()
