"""Generate a management memo via kiro-cli.

Builds a prompt from the git log and open issues, then asks ``kiro-cli`` to
write a markdown management memo analysing project direction, major
contributors, and project health.
"""

from __future__ import annotations

from .commands import run_command
from .git_log_tool import GitLog
from .issues_tool import OpenIssues

_PROMPT_TEMPLATE = """\
You are a technical program manager. Using the git activity and open issues \
below, write a management memo in GitHub-flavoured Markdown.

The memo MUST:
- Start with a top-level heading and a short executive summary.
- Analyse the DIRECTION of the project (what themes the recent work and open \
issues point toward).
- Identify the MAJOR CONTRIBUTORS (who is doing the most work, based on commit \
authorship).
- Assess the HEALTH of the project (activity level, balance of work vs. open \
issues, risks).
- Be concise and suitable for a non-technical leadership audience.
- Output Markdown only, with no surrounding commentary.

## Git activity
{git_log}

## Open issues
{issues}
"""


def build_prompt(git_log: GitLog, issues: OpenIssues) -> str:
    """Build the kiro-cli prompt from the collected log and issues."""
    return _PROMPT_TEMPLATE.format(
        git_log=git_log.to_text(),
        issues=issues.to_text(),
    )


def generate_memo(
    git_log: GitLog,
    issues: OpenIssues,
    *,
    timeout: float | None = 300,
) -> str:
    """Ask kiro-cli to produce a markdown management memo.

    Args:
        git_log: Collected git log for the period.
        issues: Collected open issues.
        timeout: Optional command timeout in seconds.

    Returns:
        The memo as a Markdown string.
    """
    prompt = build_prompt(git_log, issues)
    args = ["kiro-cli", "--prompt", prompt]
    result = run_command(args, timeout=timeout)
    return result.stdout.strip()
