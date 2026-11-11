"""Deterministic analytics for the presentation visuals.

The management memo (`memo.py`) is produced by kiro-cli and is qualitative. The
PowerPoint export, by contrast, needs small, reliable, testable summaries it can
render as the three visuals at the top of each project slide:

- :func:`health_metrics` — the activity counts behind the health classification.
- :func:`project_direction` — a single-sentence summary of where the project is
  heading, distilled from the memo's "Direction" section.
- :func:`top_contributors` — the most active people, cross-referencing commit
  authors with issue and pull-request authors (commit authorship alone
  understates who is active, in line with the memo's approach).

Everything here is pure and derived from already-collected data, so it stays
within the AGENTS.md policy (no shell, no network).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

from .git_log_tool import GitLog
from .issues_tool import IssueCollection
from .pulls_tool import PullRequestCollection

# Automated authors (CI, merge bots, dependency bots) should not count as
# human contributors. GitHub bot accounts conventionally end in "[bot]"; we
# also match a few well-known automation accounts and any login containing
# "bot" as a standalone segment (e.g. "kubernetes-prow[bot]", "renovate-bot").
_BOT_SUFFIX = re.compile(r"\[bot\]\s*$", re.IGNORECASE)
_KNOWN_BOTS = frozenset(
    {
        "dependabot", "renovate", "renovate[bot]", "github-actions",
        "github-actions[bot]", "kubernetes-prow", "k8s-ci-robot",
        "web-flow", "mergify", "mergify[bot]", "snyk-bot", "pre-commit-ci",
        "codecov", "codecov[bot]", "greenkeeper", "greenkeeper[bot]",
    }
)
_BOT_WORD = re.compile(r"(?:^|[-_\s])bot(?:$|[-_\s\[])", re.IGNORECASE)


@dataclass(frozen=True)
class HealthMetrics:
    """The quantitative activity behind the health classification."""

    category: str
    reason: str
    commits: int
    open_issues: int
    closed_issues: int
    open_pulls: int
    closed_pulls: int
    # Whether a (non-empty) ADOPTERS file was found. Presence only, not a count:
    # ADOPTERS formats are not standardised (tables, lists, or a stub linking to
    # an external page), so a count would be fragile. Folded into the health
    # visual rather than given its own visual, since many projects have none.
    has_adopters: bool = False

    @property
    def open_work(self) -> int:
        return self.open_issues + self.open_pulls

    @property
    def closed_work(self) -> int:
        return self.closed_issues + self.closed_pulls


@dataclass(frozen=True)
class Contributor:
    """A single contributor with a breakdown of how they were active."""

    name: str
    commits: int
    issues: int
    pulls: int

    @property
    def total(self) -> int:
        return self.commits + self.issues + self.pulls


def health_metrics(
    category: str,
    reason: str,
    git_log: GitLog,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
    has_adopters: bool = False,
) -> HealthMetrics:
    """Bundle the health category with the activity counts behind it.

    ``has_adopters`` indicates whether an ADOPTERS file was found; it is carried
    on the metrics so the health visual can show its presence as a one-liner.
    """
    return HealthMetrics(
        category=category,
        reason=reason,
        commits=git_log.count,
        open_issues=open_issues.count,
        closed_issues=closed_issues.count,
        open_pulls=open_pulls.count,
        closed_pulls=closed_pulls.count,
        has_adopters=has_adopters,
    )


def _normalise_author(name: str) -> str:
    """Collapse obvious variants of an author/login to a comparable key."""
    return name.strip().lower()


def is_bot(author: str) -> bool:
    """Return True if ``author`` looks like an automation/bot account.

    Matches the GitHub "[bot]" suffix convention, a list of well-known
    automation accounts, and logins with a standalone "bot" segment
    (e.g. ``kubernetes-prow[bot]``, ``renovate-bot``). Human contributions
    should be counted; automated ones should not.
    """
    if not author:
        return False
    key = author.strip().lower()
    if not key:
        return False
    if _BOT_SUFFIX.search(key):
        return True
    if key in _KNOWN_BOTS:
        return True
    if _BOT_WORD.search(key):
        return True
    return False


def top_contributors(
    git_log: GitLog,
    open_issues: IssueCollection,
    closed_issues: IssueCollection,
    open_pulls: PullRequestCollection,
    closed_pulls: PullRequestCollection,
    *,
    limit: int = 5,
) -> List[Contributor]:
    """Rank contributors by combined commit, issue, and pull-request activity.

    Commit authorship alone understates who is active, so issue and PR authors
    are folded in. People are ranked by their total number of contributions
    across all three sources, ties broken alphabetically for a stable order.
    """
    commit_counts: Counter = Counter()
    issue_counts: Counter = Counter()
    pull_counts: Counter = Counter()
    # Preserve a human-friendly display name for each normalised key.
    display: Dict[str, str] = {}

    def _record(raw: str, bucket: Counter) -> None:
        if not raw:
            return
        key = _normalise_author(raw)
        if not key or key == "unknown":
            return
        # Exclude automated accounts so the ranking reflects human work.
        if is_bot(raw):
            return
        bucket[key] += 1
        display.setdefault(key, raw.strip())

    for c in git_log.commits:
        _record(c.author_name, commit_counts)
    for coll in (open_issues, closed_issues):
        for i in coll.issues:
            _record(i.author, issue_counts)
    for coll in (open_pulls, closed_pulls):
        for p in coll.pulls:
            _record(p.author, pull_counts)

    keys = set(commit_counts) | set(issue_counts) | set(pull_counts)
    contributors = [
        Contributor(
            name=display[k],
            commits=commit_counts.get(k, 0),
            issues=issue_counts.get(k, 0),
            pulls=pull_counts.get(k, 0),
        )
        for k in keys
    ]
    contributors.sort(key=lambda c: (-c.total, c.name.lower()))
    return contributors[:limit]


def project_direction(memo_markdown: str, *, max_chars: int = 240) -> str:
    """Summarise the project's direction as a single sentence from the memo.

    Newer memos end their Direction section with an explicit, machine-readable
    one-sentence summary prefixed ``**Direction summary:**`` (the memo prompt
    requires it). We use that line verbatim when present.

    For older memos without the marker, we fall back to heuristics: a trailing
    trajectory sentence in the Direction section, then a sentence synthesised
    from the bolded theme lead-ins, then the executive summary's first sentence.

    Returns an empty string when no direction can be found.
    """
    if not memo_markdown:
        return ""

    # Preferred: the explicit marker emitted by the memo prompt.
    marked = _marked_direction_summary(memo_markdown)
    if marked:
        return _truncate_sentence(marked, max_chars)

    section = _extract_section(memo_markdown, _DIRECTION_HEADING)

    if section:
        # Prefer a trailing, non-bullet summary line that states the trajectory.
        summary = _closing_summary_sentence(section)
        if summary:
            return _truncate_sentence(summary, max_chars)

        # Otherwise synthesise one sentence from the bolded theme lead-ins.
        themes = _bold_lead_ins(section)
        if themes:
            return _truncate_sentence(_join_themes(themes), max_chars)

        # Last resort within the section: its first meaningful sentence.
        first = _first_sentence(_strip_bullets(section))
        if first:
            return _truncate_sentence(first, max_chars)

    # Fall back to the executive summary's first sentence.
    exec_section = _extract_section(memo_markdown, _EXEC_HEADING)
    if exec_section:
        first = _first_sentence(exec_section)
        if first:
            return _truncate_sentence(first, max_chars)

    return ""


def project_state_summary(memo_markdown: str) -> str:
    """Assemble the slide's project-state body from the memo.

    The body is a focused recap rather than the whole memo (which would repeat
    what the three top visuals already show). It gathers, in order:

    1. the Executive Summary,
    2. the key Risks (as bullets), and
    3. the memo's closing one-sentence overall assessment.

    New memos carry a dedicated ``## Risks`` section and an
    ``**Overall assessment:**`` marker (see the memo prompt). For older memos we
    fall back to a ``Risks:`` sub-block inside Project Health and to the last
    prose sentence of the Health section. Returns an empty string only when the
    memo has no recognisable structure at all.
    """
    if not memo_markdown:
        return ""

    parts: List[str] = []

    exec_section = _extract_section(memo_markdown, _EXEC_HEADING)
    if exec_section:
        exec_text = _strip_bullets(exec_section) or exec_section.strip()
        exec_text = _strip_inline_markdown(exec_text)
        if exec_text:
            parts.append("Executive summary")
            parts.append(exec_text)

    risks = _risk_bullets(memo_markdown)
    if risks:
        if parts:
            parts.append("")
        parts.append("Risks")
        parts.extend(f"• {r}" for r in risks)

    overall = _overall_assessment(memo_markdown)
    if overall:
        if parts:
            parts.append("")
        parts.append("Overall assessment")
        parts.append(_strip_inline_markdown(overall))

    return "\n".join(parts).strip()


def _overall_assessment(markdown: str) -> str:
    """Return the memo's closing one-sentence overall assessment.

    Prefers the explicit ``**Overall assessment:**`` marker. Falls back to the
    last plain-prose sentence of the Project Health section for older memos.
    """
    for line in markdown.splitlines():
        m = _OVERALL_MARKER.search(line.strip())
        if m:
            summary = m.group(1).strip().replace("**", "").strip()
            if summary:
                return _first_sentence(summary)

    # Fallback: the concluding sentence of the health section (older memos
    # often end it with "Overall, the project is ...").
    health = _extract_section(markdown, _HEALTH_HEADING)
    if health:
        prose = _strip_bullets(health)
        # Prefer a sentence that reads like a conclusion.
        for sentence in reversed(_split_sentences(prose)):
            lowered = sentence.lower()
            if lowered.startswith("overall") or "overall," in lowered:
                return sentence
        last = _split_sentences(prose)
        if last:
            return last[-1]
    return ""


def _risk_bullets(markdown: str, *, limit: int = 4) -> List[str]:
    """Extract the key risk statements from the memo.

    Looks first for a dedicated ``## Risks`` section, then for a ``Risks:``
    sub-block (bold or plain) inside any section. Each returned string is a
    concise risk statement with any bold lead-in label kept but markdown
    stripped.
    """
    section = _extract_section(markdown, _RISKS_HEADING)
    bullets = _bullets_of(section) if section else []

    if not bullets:
        bullets = _risk_subblock_bullets(markdown)

    cleaned = []
    for b in bullets:
        text = _clean_risk_text(b)
        if text:
            cleaned.append(text)
    return cleaned[:limit]


def _risk_subblock_bullets(markdown: str) -> List[str]:
    """Find bullets under a ``Risks:`` / ``**Risks:**`` label line (older memos)."""
    lines = markdown.splitlines()
    collecting = False
    bullets: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not collecting:
            # A label line like "**Risks:**", "Risks:", or "Risks to monitor:".
            bare = stripped.replace("*", "").strip()
            label = bare.rstrip(":").strip().lower()
            if label in ("risks", "risks to monitor", "key risks") and bare.endswith(":"):
                collecting = True
            continue
        # Stop at the next heading or label line.
        if _HEADING_LINE.match(line):
            break
        m = _BULLET_LINE.match(line)
        if m:
            bullets.append(m.group(1).strip())
        elif stripped and not stripped.endswith(":") and not bullets:
            # Non-bullet prose right after the label and before any bullet;
            # ignore and keep scanning for bullets.
            continue
        elif not stripped:
            continue
        elif bullets and not m:
            # A non-bullet, non-empty line after we have collected bullets ends
            # the sub-block.
            break
    return bullets


def _clean_risk_text(bullet: str) -> str:
    """Trim a risk bullet to a concise statement.

    Keeps a bold lead-in label (e.g. "Key-person concentration:") but strips
    markdown emphasis, and shortens long explanatory bodies to the lead-in plus
    first sentence.
    """
    text = bullet.strip()
    lead = _BOLD_LEAD.match(text)
    if lead:
        label = _strip_inline_markdown(lead.group(1).strip().rstrip("."))
        rest = _strip_inline_markdown(text[lead.end():].strip())
        first = _first_sentence(rest)
        if first:
            return f"{label}: {first.rstrip('.')}."
        return f"{label}."
    # No bold label: just take the first sentence, markdown stripped.
    return _first_sentence(_strip_inline_markdown(text))


def _bullets_of(section: str) -> List[str]:
    """Return the top-level bullet texts of a section."""
    bullets = []
    for line in section.splitlines():
        m = _BULLET_LINE.match(line)
        if m:
            bullets.append(m.group(1).strip())
    return bullets


def _split_sentences(text: str) -> List[str]:
    """Split prose into sentences (coarse, period/!/? based)."""
    text = text.strip()
    if not text:
        return []
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def _strip_inline_markdown(text: str) -> str:
    """Remove inline emphasis/code markers so prose reads cleanly on a slide."""
    return text.replace("**", "").replace("`", "").strip()


# Explicit one-sentence direction summary emitted by the memo prompt, e.g.
# "**Direction summary:** The project is in a maturity-focused phase.". The
# bold markers are optional so a memo that drops them still matches.
_DIRECTION_SUMMARY_MARKER = re.compile(
    r"\*{0,2}Direction summary\*{0,2}\s*:\s*\*{0,2}\s*(.+)",
    re.IGNORECASE,
)

# Explicit one-sentence overall bottom-line judgement, emitted by the memo
# prompt as the memo's final line, e.g. "**Overall assessment:** A well-run
# project...". Bold markers optional.
_OVERALL_MARKER = re.compile(
    r"\*{0,2}Overall assessment\*{0,2}\s*:\s*\*{0,2}\s*(.+)",
    re.IGNORECASE,
)

# Headings vary between memos ("Direction of the Project" vs "Project
# Direction"); match any level-2+ heading whose text contains "direction".
_DIRECTION_HEADING = re.compile(r"direction", re.IGNORECASE)
_EXEC_HEADING = re.compile(r"executive summary", re.IGNORECASE)
_RISKS_HEADING = re.compile(r"\brisks?\b", re.IGNORECASE)
_HEALTH_HEADING = re.compile(r"health", re.IGNORECASE)
_HEADING_LINE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*#*\s*$")
_BULLET_LINE = re.compile(r"^\s*[-*+]\s+(.*)$")
# A line whose first non-space content is bold, e.g. a bullet
# "- **Theme.** ..." or a bolded paragraph "**1. Theme.** ...".
_BOLD_LEAD = re.compile(r"^\s*(?:[-*+]\s+)?\*\*(.+?)\*\*")
# A leading enumerator inside a theme, e.g. "1. " or "2) ".
_LEADING_ENUM = re.compile(r"^\s*\d+[.)]\s*")
# Parenthetical qualifiers like "(primary focus)" or "(dominant)".
_PAREN_QUALIFIER = re.compile(r"\s*\([^)]*\)\s*")


def _marked_direction_summary(markdown: str) -> str:
    """Return the sentence after the ``**Direction summary:**`` marker, if any.

    This is the explicit one-liner the memo prompt asks kiro-cli to append to
    the Direction section. Extracting it is unambiguous, so it is preferred over
    any heuristic. Returns an empty string when the marker is absent.
    """
    for line in markdown.splitlines():
        m = _DIRECTION_SUMMARY_MARKER.search(line.strip())
        if not m:
            continue
        summary = m.group(1).strip().replace("**", "").strip()
        if summary:
            return _first_sentence(summary)
    return ""


def _extract_section(markdown: str, heading_pattern: re.Pattern) -> str:
    """Return the body of the first heading matching ``heading_pattern``.

    The body runs from just after the matching heading up to (but not
    including) the next heading of the same or higher level.
    """
    lines = markdown.splitlines()
    start = None
    start_level = 0
    for idx, line in enumerate(lines):
        m = _HEADING_LINE.match(line)
        if not m:
            continue
        if start is None:
            if heading_pattern.search(m.group(1)):
                start = idx + 1
                start_level = len(line) - len(line.lstrip("#").lstrip())
                # Count the leading '#'s for the level.
                start_level = len(line) - len(line.lstrip("#"))
            continue
        # We're past the start; stop at the next heading of >= level.
        level = len(line) - len(line.lstrip("#"))
        if level <= start_level:
            return "\n".join(lines[start:idx]).strip()
    if start is not None:
        return "\n".join(lines[start:]).strip()
    return ""


def _strip_bullets(section: str) -> str:
    """Return the plain-prose lines of a section joined into text.

    Excludes bullets, headings, and bolded/enumerated theme paragraphs, leaving
    only the introductory and summary prose.
    """
    prose = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _BULLET_LINE.match(line) or _HEADING_LINE.match(line):
            continue
        if _BOLD_LEAD.match(line) or _LEADING_ENUM.match(stripped):
            continue
        prose.append(stripped)
    return " ".join(prose).strip()


def _closing_summary_sentence(section: str) -> str:
    """Return the trailing prose summary of a direction section, if any.

    Memos often end the direction section with a single summary sentence after
    the themes (e.g. "The net direction is ..."). That closing line is exactly
    the one-sentence direction we want. We only accept a *plain prose* line:
    not a bullet, not a bolded theme lead-in, and not an enumerated theme — so
    the last theme paragraph is not mistaken for a trajectory statement.
    """
    lines = section.splitlines()
    # Index of the last theme line (bullet / bold / enumerated). A genuine
    # closing summary comes *after* the themes; prose before them is an intro.
    last_theme = -1
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _BULLET_LINE.match(line) or _BOLD_LEAD.match(line) or (
            stripped and _LEADING_ENUM.match(stripped)
        ):
            last_theme = idx

    candidates = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_LINE.match(line) or _BULLET_LINE.match(line):
            continue
        if _BOLD_LEAD.match(line) or _LEADING_ENUM.match(stripped):
            continue
        # Only prose that follows the themes can be a closing summary. When
        # there are no themes at all (last_theme == -1), any prose qualifies.
        if last_theme >= 0 and idx < last_theme:
            continue
        candidates.append(stripped)
    if not candidates:
        return ""
    tail = candidates[-1]
    if _looks_like_lead_in(tail):
        return ""
    return _first_sentence(tail)


def _looks_like_lead_in(text: str) -> bool:
    lowered = text.lower()
    return (
        lowered.endswith(":")
        or "points to" in lowered
        or "themes emerge" in lowered
        or "themes define" in lowered
        or ("themes" in lowered and "heading" in lowered)
    )


def _demote_theme_case(theme: str) -> str:
    """Lowercase the first letter of a theme unless it begins an acronym.

    "Helm plugin hardening" -> "helm plugin hardening", but "API modernization"
    and "CLI usability" keep their capitals so acronyms aren't mangled.
    """
    if not theme:
        return theme
    first_word = theme.split(None, 1)[0]
    # Treat the first word as an acronym if it has an interior capital or is all
    # caps (e.g. "API", "gRPC", "FRR"), in which case leave the case untouched.
    core = first_word.strip(".,:;")
    if len(core) >= 2 and core[1:] != core[1:].lower():
        return theme
    return theme[0].lower() + theme[1:]


def _bold_lead_ins(section: str) -> List[str]:
    """Extract the bolded theme lead-ins from a direction section.

    Handles both bulleted themes ("- **Theme.** ...") and bolded paragraph
    themes ("**1. Theme.** ..."), stripping any leading "1." enumerator and
    trailing parenthetical qualifiers like "(primary focus)".
    """
    themes: List[str] = []
    for line in section.splitlines():
        bold = _BOLD_LEAD.match(line)
        if not bold:
            continue
        theme = bold.group(1).strip()
        theme = _LEADING_ENUM.sub("", theme)  # drop "1. " / "2) "
        theme = theme.rstrip(".")
        theme = _PAREN_QUALIFIER.sub(" ", theme).strip().rstrip(".").strip()
        if theme:
            themes.append(_demote_theme_case(theme))
    return themes


def _join_themes(themes: List[str]) -> str:
    """Render a list of themes into a single readable sentence."""
    themes = themes[:4]
    if len(themes) == 1:
        body = themes[0]
    elif len(themes) == 2:
        body = f"{themes[0]} and {themes[1]}"
    else:
        body = ", ".join(themes[:-1]) + f", and {themes[-1]}"
    return f"The project is focused on {body}."


def _first_sentence(text: str) -> str:
    """Return the first sentence of ``text`` (up to the first period).

    Leading markdown emphasis and list enumerators (e.g. "**3. ") are stripped
    first so they are not mistaken for a complete one-character "sentence".
    """
    text = text.strip().lstrip("*").strip()
    text = _LEADING_ENUM.sub("", text)
    if not text:
        return ""
    # Split on sentence-ending punctuation followed by whitespace and a capital
    # or end of text, so abbreviations/enumerators like "v1." don't end it
    # prematurely. Require at least a few characters before the terminator.
    match = re.search(r"(.{12,}?[.!?])(\s+|$)", text)
    if match:
        return match.group(1).strip().replace("**", "")
    return text.replace("**", "")


def _truncate_sentence(text: str, max_chars: int) -> str:
    """Trim overly long sentences on a word boundary with an ellipsis."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"
