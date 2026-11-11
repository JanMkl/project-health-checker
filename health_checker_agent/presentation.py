"""Optional PowerPoint export of the fleet findings.

Builds a ``.pptx`` deck with one slide per project plus a final overall summary
slide. Each project slide follows a fixed structure:

- A title with the repository name.
- Three "visuals" across the top of the slide, side by side:
    1. **Project health** — the health category and the activity counts behind
       it.
    2. **Project direction** — a single-sentence summary of where the project
       is heading, distilled from the memo.
    3. **Top contributors** — the most active people across commits, issues,
       and pull requests.
- Below the visuals, a focused recap of the project state — the executive
  summary, the key risks, and the memo's closing overall assessment — rather
  than the full memo (which would repeat the top visuals).

Each section sits inside a bordered, lightly-shaded panel so the visuals are
clearly separated. The palette is intentionally conservative: a neutral grey
fill with a soft grey border, and only a faint category-tinted fill behind the
health panel.

The deck depends on ``python-pptx``, which is an optional dependency (install
the ``pptx`` extra or ``python-pptx`` directly). The import is deferred so the
rest of the agent works without it; calling :func:`build_presentation` without
it raises a clear error.

Only the deterministic analytics (``analytics.py``) and already-collected data
are used here, so this module performs no shell or network access, in line with
AGENTS.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

from .analytics import (
    Contributor,
    HealthMetrics,
    health_metrics,
    project_direction,
    project_state_summary,
    top_contributors,
)
from .health import ATTENTION, FAILED, HEALTHY, INVESTIGATE

# Human-readable labels for the health categories.
_CATEGORY_LABELS = {
    HEALTHY: "Healthy",
    ATTENTION: "Needs attention",
    INVESTIGATE: "Investigate",
    FAILED: "Failed to analyse",
}

# RGB accent colours per category (used for the health visual title).
_CATEGORY_COLORS = {
    HEALTHY: (0x2E, 0x7D, 0x32),      # green
    ATTENTION: (0xC6, 0x28, 0x28),    # red
    INVESTIGATE: (0xF5, 0x7F, 0x17),  # amber
    FAILED: (0x61, 0x61, 0x61),       # grey
}

# Conservative panel palette for the bordered boxes behind each section. A
# neutral light-grey fill with a soft grey border keeps the slides calm; the
# health panel gets a very light category-tinted fill so it reads at a glance
# without making the deck colourful.
_PANEL_FILL = (0xF4, 0xF5, 0xF7)        # near-white neutral grey
_PANEL_BORDER = (0xC8, 0xCD, 0xD3)      # soft grey border
_BODY_PANEL_FILL = (0xFA, 0xFB, 0xFC)   # slightly lighter for the large body

# Very light category-tinted fills for the health panel (kept subtle).
_CATEGORY_PANEL_FILL = {
    HEALTHY: (0xEC, 0xF3, 0xEC),      # faint green
    ATTENTION: (0xF6, 0xEC, 0xEC),    # faint red
    INVESTIGATE: (0xF6, 0xF1, 0xE8),  # faint amber
    FAILED: (0xF0, 0xF0, 0xF0),       # faint grey
}


class PptxNotInstalledError(RuntimeError):
    """Raised when python-pptx is required but not importable."""


@dataclass(frozen=True)
class ProjectSlideData:
    """Everything needed to render a single project slide."""

    repo: str
    health: HealthMetrics
    direction: str                # one-sentence summary of project direction
    contributors: List[Contributor]
    state_text: str               # prose describing the overall project state


def _require_pptx():
    """Import python-pptx lazily, raising a friendly error if it's missing."""
    try:
        import pptx  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise PptxNotInstalledError(
            "The PowerPoint export requires python-pptx. Install it with "
            "'pip install python-pptx' (or 'pip install -e .[pptx]')."
        ) from exc
    return pptx


def _strip_markdown(text: str) -> str:
    """Reduce memo Markdown to plain prose suitable for a slide body.

    Strips code fences, heading markers, list bullets, and inline emphasis so
    the project-state text reads cleanly in PowerPoint. Kept intentionally
    simple; it is a presentation aid, not a full Markdown renderer.
    """
    lines: List[str] = []
    in_fence = False
    for raw in text.splitlines():
        line = raw.rstrip()
        fence = line.lstrip()
        if fence.startswith("```") or fence.startswith("~~~"):
            # Drop the fence markers but keep any code content as plain text.
            in_fence = not in_fence
            continue
        # Headings -> plain text.
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        # List bullets -> bullet dot.
        line = re.sub(r"^\s*[-*+]\s+", "• ", line)
        line = re.sub(r"^\s*\d+\.\s+", "• ", line)
        # Inline emphasis / code.
        line = line.replace("**", "").replace("`", "")
        line = re.sub(r"(?<!\*)\*(?!\*)", "", line)
        lines.append(line)

    # Collapse runs of blank lines.
    out: List[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank and out:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).strip()


def build_project_slide_data(result, state_text: str | None = None) -> ProjectSlideData:
    """Derive :class:`ProjectSlideData` from a ``RepoResult``.

    Args:
        result: A ``RepoResult`` (duck-typed; see ``agent.RepoResult``).
        state_text: Optional override for the project-state prose. Defaults to a
            focused recap of the memo (executive summary, risks, and the closing
            overall assessment) rather than the full memo, so it does not repeat
            what the three top visuals already show.
    """
    # Adopters is optional context (not every project publishes a list); fold
    # its presence into the health visual rather than giving it a visual of its
    # own. Presence only, not a count — ADOPTERS formats vary too much to count
    # reliably; the AI memo carries the qualitative detail.
    adopters = getattr(result, "adopters", None)
    has_adopters = bool(adopters is not None and adopters.found)

    metrics = health_metrics(
        result.assessment.category,
        result.assessment.reason,
        result.git_log,
        result.open_issues,
        result.closed_issues,
        result.open_pulls,
        result.closed_pulls,
        has_adopters=has_adopters,
    )
    direction = project_direction(result.memo_markdown)
    contributors = top_contributors(
        result.git_log,
        result.open_issues,
        result.closed_issues,
        result.open_pulls,
        result.closed_pulls,
    )
    if state_text is None:
        # Focused recap: executive summary + risks + overall assessment. Fall
        # back to the stripped full memo only if the recap comes up empty
        # (e.g. an unstructured memo).
        state_text = project_state_summary(result.memo_markdown)
        if not state_text:
            state_text = _strip_markdown(result.memo_markdown)

    return ProjectSlideData(
        repo=result.repo,
        health=metrics,
        direction=direction,
        contributors=contributors,
        state_text=state_text,
    )


# --- Rendering ------------------------------------------------------------


def _add_panel(slide, left, top, width, height, *, fill, border=_PANEL_BORDER):
    """Draw a bordered, lightly-filled rounded rectangle to group a section.

    The panel is added first so later text boxes render on top of it.

    Args:
        slide: The slide to add the panel to.
        left, top, width, height: EMU geometry.
        fill: (r, g, b) fill colour.
        border: (r, g, b) border colour.
    """
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Pt
    from pptx.dml.color import RGBColor

    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(*fill)
    shape.line.color.rgb = RGBColor(*border)
    shape.line.width = Pt(1)
    shape.shadow.inherit = False
    # No text in the panel itself; it is purely a background container.
    shape.text_frame.paragraphs[0].text = ""
    return shape


def _add_visual_box(slide, left, top, width, height, title, lines, *, accent=None,
                    panel_fill=_PANEL_FILL):
    """Add one of the three top visuals inside a bordered panel.

    A background panel is drawn first, then the title and body text are placed
    inside it with a little padding so each section is clearly separated.

    Args:
        slide: The slide to add to.
        left, top, width, height: EMU positions/sizes of the panel.
        title: Heading shown at the top of the box.
        lines: Sequence of body lines (strings).
        accent: Optional (r, g, b) tuple to colour the title.
        panel_fill: (r, g, b) fill colour for the background panel.
    """
    from pptx.util import Pt, Emu
    from pptx.dml.color import RGBColor

    from pptx.util import Inches as _Inches

    _add_panel(slide, left, top, width, height, fill=panel_fill)

    # Inset the text inside the panel for padding.
    pad = Emu(int(_Inches(0.12)))
    box = slide.shapes.add_textbox(
        left + pad, top + pad, width - 2 * pad, height - 2 * pad
    )
    tf = box.text_frame
    tf.word_wrap = True

    heading = tf.paragraphs[0]
    run = heading.add_run()
    run.text = title
    run.font.bold = True
    run.font.size = Pt(16)
    if accent is not None:
        run.font.color.rgb = RGBColor(*accent)

    for line in lines:
        para = tf.add_paragraph()
        run = para.add_run()
        run.text = line
        run.font.size = Pt(12)
    return box


def _adopters_line(health: HealthMetrics) -> str:
    """One-liner about adopters presence, folded into the health visual.

    Presence only: ADOPTERS formats are not standardised, so we report whether a
    list exists rather than a (fragile) count.
    """
    if health.has_adopters:
        return "\u2b50 Adopters: documented"
    return "Adopters: none listed"


def _health_lines(health: HealthMetrics) -> List[str]:
    label = _CATEGORY_LABELS.get(health.category, health.category)
    return [
        label,
        f"Commits: {health.commits}",
        f"Open: {health.open_work} (issues {health.open_issues}, PRs {health.open_pulls})",
        f"Closed: {health.closed_work} (issues {health.closed_issues}, PRs {health.closed_pulls})",
        _adopters_line(health),
    ]


def _direction_lines(direction: str) -> List[str]:
    if not direction:
        return ["(direction not available)"]
    return [direction]


def _contributor_lines(contributors: Sequence[Contributor]) -> List[str]:
    if not contributors:
        return ["(no contributors found)"]
    lines = []
    for c in contributors:
        lines.append(
            f"• {c.name} — {c.total} (c{c.commits}/i{c.issues}/p{c.pulls})"
        )
    return lines


def _add_project_slide(prs, data: ProjectSlideData) -> None:
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    slide_width = prs.slide_width

    # Title.
    title_box = slide.shapes.add_textbox(
        Inches(0.4), Inches(0.2), slide_width - Inches(0.8), Inches(0.7)
    )
    title_tf = title_box.text_frame
    title_tf.word_wrap = True
    run = title_tf.paragraphs[0].add_run()
    run.text = data.repo
    run.font.bold = True
    run.font.size = Pt(28)

    # Three visuals across the top.
    margin = Inches(0.4)
    gap = Inches(0.3)
    usable = slide_width - 2 * margin - 2 * gap
    col_w = int(usable / 3)
    top = Inches(1.0)
    vis_h = Inches(2.2)

    _add_visual_box(
        slide, margin, top, col_w, vis_h,
        "Project health", _health_lines(data.health),
        accent=_CATEGORY_COLORS.get(data.health.category),
        panel_fill=_CATEGORY_PANEL_FILL.get(data.health.category, _PANEL_FILL),
    )
    _add_visual_box(
        slide, margin + col_w + gap, top, col_w, vis_h,
        "Project direction", _direction_lines(data.direction),
    )
    _add_visual_box(
        slide, margin + 2 * (col_w + gap), top, col_w, vis_h,
        "Top contributors", _contributor_lines(data.contributors),
    )

    # Project state body below the visuals, inside its own bordered panel.
    body_top = top + vis_h + Inches(0.2)
    body_h = prs.slide_height - body_top - Inches(0.3)
    body_w = slide_width - 2 * margin
    _add_panel(slide, margin, body_top, body_w, body_h, fill=_BODY_PANEL_FILL)

    pad = Inches(0.12)
    body_box = slide.shapes.add_textbox(
        margin + pad, body_top + pad, body_w - 2 * pad, body_h - 2 * pad
    )
    body_tf = body_box.text_frame
    body_tf.word_wrap = True
    head = body_tf.paragraphs[0].add_run()
    head.text = "Project state"
    head.font.bold = True
    head.font.size = Pt(16)

    state = data.state_text or "(no memo text available)"
    for line in state.splitlines():
        para = body_tf.add_paragraph()
        run = para.add_run()
        run.text = line
        run.font.size = Pt(11)


def _add_summary_slide(prs, fleet_data: Sequence[ProjectSlideData]) -> None:
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_width = prs.slide_width

    title_box = slide.shapes.add_textbox(
        Inches(0.4), Inches(0.2), slide_width - Inches(0.8), Inches(0.7)
    )
    run = title_box.text_frame.paragraphs[0].add_run()
    run.text = "Overall summary"
    run.font.bold = True
    run.font.size = Pt(28)

    # Tally categories across the fleet.
    counts = {HEALTHY: 0, ATTENTION: 0, INVESTIGATE: 0, FAILED: 0}
    for d in fleet_data:
        counts[d.health.category] = counts.get(d.health.category, 0) + 1
    total = len(fleet_data)

    panel_left = Inches(0.4)
    panel_top = Inches(1.1)
    panel_w = slide_width - Inches(0.8)
    panel_h = prs.slide_height - Inches(1.5)
    _add_panel(slide, panel_left, panel_top, panel_w, panel_h, fill=_BODY_PANEL_FILL)

    pad = Inches(0.12)
    body_box = slide.shapes.add_textbox(
        panel_left + pad, panel_top + pad, panel_w - 2 * pad, panel_h - 2 * pad
    )
    tf = body_box.text_frame
    tf.word_wrap = True
    summary = (
        f"{total} project{'s' if total != 1 else ''} analysed: "
        f"{counts[ATTENTION]} need attention, "
        f"{counts[INVESTIGATE]} to investigate, "
        f"{counts[HEALTHY]} healthy"
    )
    if counts.get(FAILED):
        summary += f", {counts[FAILED]} failed to analyse"
    summary += "."
    first = tf.paragraphs[0].add_run()
    first.text = summary
    first.font.size = Pt(14)
    first.font.bold = True

    # Order most-urgent first, matching the fleet report.
    order = [ATTENTION, INVESTIGATE, HEALTHY, FAILED]
    for category in order:
        bucket = [d for d in fleet_data if d.health.category == category]
        if not bucket:
            continue
        head = tf.add_paragraph()
        head_run = head.add_run()
        head_run.text = f"{_CATEGORY_LABELS[category]} ({len(bucket)})"
        head_run.font.bold = True
        head_run.font.size = Pt(13)
        for d in sorted(bucket, key=lambda x: x.repo.lower()):
            para = tf.add_paragraph()
            run = para.add_run()
            run.text = f"• {d.repo} — {d.health.reason}"
            run.font.size = Pt(11)


def build_presentation(results: Sequence, output_path: str) -> str:
    """Build the PowerPoint deck and write it to ``output_path``.

    Args:
        results: An iterable of ``RepoResult`` objects (duck-typed).
        output_path: Destination ``.pptx`` path. The caller is responsible for
            ensuring this stays within the permitted output directory.

    Returns:
        The ``output_path`` that was written.

    Raises:
        PptxNotInstalledError: If python-pptx is not installed.
    """
    _require_pptx()
    from pptx import Presentation

    prs = Presentation()

    slide_data = [build_project_slide_data(r) for r in results]
    for data in slide_data:
        _add_project_slide(prs, data)

    # Final overall summary slide across all projects.
    _add_summary_slide(prs, slide_data)

    prs.save(output_path)
    return output_path
