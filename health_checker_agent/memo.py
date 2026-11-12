"""Generate a management memo via a pluggable AI-CLI backend.

Builds a prompt from the git log, issues (open + closed), pull requests
(open + closed), the project's ADOPTERS list, its security policy, and its
OWNERS file (when found), then asks an AI coding CLI (``kiro-cli`` by default,
or ``codex`` / ``cursor-agent``) to write a markdown management memo analysing
project direction, active contributors, adopters, security process, governance,
and project health.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .backends import DEFAULT_BACKEND, get_backend
from .commands import run_command
from .git_log_tool import GitLog
from .issues_tool import IssueCollection
from .pulls_tool import PullRequestCollection

if TYPE_CHECKING:  # avoid an import cycle at runtime; only needed for typing
    from .adopters_tool import Adopters
    from .owners_tool import Owners
    from .security_tool import SecurityPolicy

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
- "## Adopters" — base this section on the "Adopters" data below. The ADOPTERS \
file format is not standardised: it may be a table or list of organisations, or \
it may just be a short stub that links to an external adopters page without \
naming anyone inline. Treat the PRESENCE of an ADOPTERS file as meaningful in \
itself — it signals the project has a recognised adopter community and \
real-world usage — even when you cannot extract individual organisations from \
the content. So: if specific organisations are listed, summarise who is using \
the project and call out notable names. If an ADOPTERS file is present but does \
not enumerate organisations inline (e.g. it points to an external page), still \
state that the project maintains a public adopters list (and mention the linked \
page if given), without implying the list is empty. Only if NO ADOPTERS file \
was found at all, state briefly that no public adopters list is available. \
Never invent adopters.
- "## Security Process" — base this section on the "Security policy" data \
below. The presence of a SECURITY.md or SECURITY_CONTACTS file means the \
project has a documented security disclosure and response process. If a policy \
is present, briefly describe how vulnerabilities are reported and handled, then \
assess whether it follows responsible-disclosure best practices — look for: a \
PRIVATE reporting channel (a security email, GitHub private vulnerability \
reporting, or similar) rather than public issues; a stated response/triage \
timeline or acknowledgement expectation; coordinated disclosure / embargo \
handling; and named security contacts or a security team. Call out any of these \
that are clearly present or clearly missing. If NO security policy file was \
found, state that the project has no documented security disclosure process, \
and flag this as a security-governance gap. Do not invent policy details that \
are not in the provided content.
- "## Governance (Owners)" — base this section on the "Owners" data below. An \
OWNERS file lists the project's reviewers and approvers/maintainers (the people \
with rights to merge pull requests). If an OWNERS file is present, note that \
the project transparently documents who holds merge authority, and briefly \
characterise it (e.g. the number of reviewers/approvers, or whether it \
delegates to aliases/teams) as a signal of governance maturity and bus-factor. \
If NO OWNERS file was found, state that the project does not publish an OWNERS \
file, so merge-authority and reviewer transparency cannot be confirmed from it \
(without assuming the project is poorly governed — not all projects use this \
convention). Do not invent names.
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

## Adopters
{adopters}

## Security policy
{security}

## Owners
{owners}
"""

_NO_ADOPTERS_TEXT = "(no ADOPTERS file found)"
_NO_SECURITY_TEXT = "(no SECURITY.md or SECURITY_CONTACTS file found)"
_NO_OWNERS_TEXT = "(no OWNERS file found)"


def build_prompt(
    git_log: GitLog,
    *,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
    adopters: "Adopters | None" = None,
    security: "SecurityPolicy | None" = None,
    owners: "Owners | None" = None,
) -> str:
    """Build the AI-CLI prompt from the collected activity."""
    adopters_text = adopters.to_text() if adopters is not None else _NO_ADOPTERS_TEXT
    security_text = security.to_text() if security is not None else _NO_SECURITY_TEXT
    owners_text = owners.to_text() if owners is not None else _NO_OWNERS_TEXT
    return _PROMPT_TEMPLATE.format(
        git_log=git_log.to_text(),
        open_issues=open_issues.to_text(),
        closed_issues=closed_issues.to_text(),
        open_pulls=open_pulls.to_text(),
        closed_pulls=closed_pulls.to_text(),
        adopters=adopters_text,
        security=security_text,
        owners=owners_text,
    )


def generate_memo(
    git_log: GitLog,
    *,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
    adopters: "Adopters | None" = None,
    security: "SecurityPolicy | None" = None,
    owners: "Owners | None" = None,
    backend: str = DEFAULT_BACKEND,
    timeout: float | None = 300,
) -> str:
    """Ask an AI-CLI backend to produce a markdown management memo.

    Args:
        git_log: Collected git log for the period.
        open_issues: Open issues.
        closed_issues: Closed issues.
        open_pulls: Open pull requests.
        closed_pulls: Closed pull requests.
        adopters: Optional ADOPTERS information for the project.
        security: Optional security-policy information for the project.
        owners: Optional OWNERS (reviewers/maintainers) information.
        backend: Which AI CLI to invoke (``kiro-cli``, ``codex``, or
            ``cursor-agent``).
        timeout: Optional command timeout in seconds.

    Returns:
        The memo as a Markdown string.

    Raises:
        UnknownBackendError: If ``backend`` is not supported.
    """
    prompt = build_prompt(
        git_log,
        open_issues=open_issues,
        closed_issues=closed_issues,
        open_pulls=open_pulls,
        closed_pulls=closed_pulls,
        adopters=adopters,
        security=security,
        owners=owners,
    )
    # Each backend runs its tool non-interactively, feeding the prompt on stdin
    # (prompts for large repos can exceed the OS argument-length limit) and
    # returning just the memo text. run_command is injected so the backend's
    # shell access still goes through the AGENTS.md allow-list.
    return get_backend(backend).generate(prompt, run_command, timeout)
