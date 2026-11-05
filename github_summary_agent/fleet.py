"""Fleet roll-up report across all analysed repositories.

Groups repos into management-attention buckets using the deterministic
:mod:`health` classification and renders a single Markdown report that links to
each per-repo memo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from .health import ATTENTION, HEALTHY, INVESTIGATE, HealthAssessment


@dataclass(frozen=True)
class RepoOutcome:
    """Per-repo result needed for the roll-up."""

    repo: str
    assessment: HealthAssessment
    memo_path: str
    analysed: bool  # True if re-analysed this run, False if reused


_CATEGORY_TITLES = {
    ATTENTION: "Requires management attention",
    INVESTIGATE: "Needs investigation / keep an eye on",
    HEALTHY: "Healthy (no attention needed)",
}

# Order the buckets most-urgent first.
_CATEGORY_ORDER = [ATTENTION, INVESTIGATE, HEALTHY]


def build_fleet_report(outcomes: List[RepoOutcome], *, output_dir: str) -> str:
    """Render the fleet roll-up as Markdown.

    Args:
        outcomes: One :class:`RepoOutcome` per repository.
        output_dir: Directory the memos live in, used to produce relative links.
    """
    total = len(outcomes)
    counts = {cat: 0 for cat in _CATEGORY_ORDER}
    for o in outcomes:
        counts[o.assessment.category] = counts.get(o.assessment.category, 0) + 1

    lines: List[str] = ["# Fleet Health Report", ""]
    lines.append(
        f"Analysed {total} repositor{'y' if total == 1 else 'ies'}: "
        f"{counts[ATTENTION]} requiring attention, "
        f"{counts[INVESTIGATE]} to investigate, "
        f"{counts[HEALTHY]} healthy."
    )
    lines.append("")

    for category in _CATEGORY_ORDER:
        bucket = [o for o in outcomes if o.assessment.category == category]
        lines.append(f"## {_CATEGORY_TITLES[category]} ({len(bucket)})")
        lines.append("")
        if not bucket:
            lines.append("_None._")
            lines.append("")
            continue
        for o in sorted(bucket, key=lambda x: x.repo):
            rel = os.path.relpath(o.memo_path, output_dir)
            reused = "" if o.analysed else " _(reused existing memo)_"
            lines.append(f"- **{o.repo}** — {o.assessment.reason} [memo]({rel}){reused}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
