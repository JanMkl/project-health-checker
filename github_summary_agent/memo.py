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

The memo MUST:
- Start with a top-level heading and a short executive summary.
- Analyse the DIRECTION of the project (what themes the recent commits, issues, \
and pull requests point toward).
- Identify the ACTIVE CONTRIBUTORS AND COMMUNITY MEMBERS. Do NOT rely on commit \
authorship alone; many active members contribute mainly by opening and \
resolving issues and by authoring and reviewing pull requests. Cross-reference \
commit authors with issue and pull-request authors to find who is genuinely \
active, and call out community members who are active in issues/PRs even if \
they have few or no commits.
- Assess the HEALTH of the project (activity level, how open work compares to \
what is being closed/merged, responsiveness, and risks).
- Be concise and suitable for a non-technical leadership audience.
- Output Markdown only, with no surrounding commentary.

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
    # kiro-cli takes the prompt as the positional INPUT to the `chat`
    # subcommand. `--no-interactive` runs it without expecting user input and
    # `--trust-all-tools` avoids blocking on tool-permission prompts.
    args = [
        "kiro-cli",
        "chat",
        "--no-interactive",
        "--trust-all-tools",
        prompt,
    ]
    result = run_command(args, timeout=timeout)
    return result.stdout.strip()
