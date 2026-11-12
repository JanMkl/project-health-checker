import os
import tempfile
import unittest
from dataclasses import dataclass
from typing import List
from unittest import mock

from typing import Optional

from health_checker_agent import presentation
from health_checker_agent.adopters_tool import Adopters
from health_checker_agent.owners_tool import Owners
from health_checker_agent.security_tool import SecurityPolicy
from health_checker_agent.analytics import HealthMetrics
from health_checker_agent.git_log_tool import Commit, GitLog
from health_checker_agent.health import ATTENTION, HEALTHY, HealthAssessment
from health_checker_agent.issues_tool import Issue, IssueCollection
from health_checker_agent.presentation import (
    PptxNotInstalledError,
    _health_lines,
    _strip_markdown,
    build_presentation,
    build_project_slide_data,
)
from health_checker_agent.pulls_tool import PullRequest, PullRequestCollection


@dataclass
class FakeResult:
    """Duck-typed stand-in for agent.RepoResult."""

    repo: str
    git_log: GitLog
    open_issues: IssueCollection
    closed_issues: IssueCollection
    open_pulls: PullRequestCollection
    closed_pulls: PullRequestCollection
    assessment: HealthAssessment
    memo_markdown: str
    adopters: Optional[Adopters] = None
    security: Optional[SecurityPolicy] = None
    owners: Optional[Owners] = None


_DEFAULT_MEMO = (
    "# Memo\n\n"
    "## Executive Summary\n"
    "A healthy, active scheduler project.\n\n"
    "## Project Direction\n"
    "- **Scheduler reliability.** work.\n"
    "The overall trajectory is scheduler reliability hardening.\n\n"
    "## Project Health\n"
    "Throughput is high.\n\n"
    "## Risks\n"
    "- **Bus factor.** One maintainer does most of the work.\n\n"
    "**Overall assessment:** A well-run project with a single-maintainer risk.\n"
)


def _result(repo, category, *, commits=2, memo=_DEFAULT_MEMO, adopters=None, security=None, owners=None):
    log = GitLog(
        since="x",
        until=None,
        commits=[
            Commit(f"h{i}", "alice", "a@x", "2026-10-01", "Add scheduler retries")
            for i in range(commits)
        ],
    )
    open_i = IssueCollection(
        repo=repo,
        state="open",
        issues=[Issue(1, "scheduler latency", "bob", "2026-10-01", "open")],
    )
    closed_i = IssueCollection(repo=repo, state="closed", issues=[])
    open_p = PullRequestCollection(
        repo=repo,
        state="open",
        pulls=[PullRequest(2, "scheduler fairness", "bob", "2026-10-01", "open")],
    )
    closed_p = PullRequestCollection(repo=repo, state="closed", pulls=[])
    return FakeResult(
        repo=repo,
        git_log=log,
        open_issues=open_i,
        closed_issues=closed_i,
        open_pulls=open_p,
        closed_pulls=closed_p,
        assessment=HealthAssessment(repo, category, f"reason for {repo}"),
        memo_markdown=memo,
        adopters=adopters,
        security=security,
        owners=owners,
    )


def _adopters(repo, present):
    """Build an Adopters that is present (any content) or absent."""
    if present:
        # Content shape is irrelevant to presence; use a simple stub.
        return Adopters(
            repo=repo,
            source="o/community:ADOPTERS.md",
            content="# Adopters\n\n- Ericsson\n- Red Hat\n",
        )
    return Adopters(repo=repo, source=None, content=None)


def _security(repo, present):
    """Build a SecurityPolicy that is present (any content) or absent."""
    if present:
        return SecurityPolicy(
            repo=repo,
            source="o/r:SECURITY.md",
            content="# Security Policy\n\nReport privately to security@example.com",
        )
    return SecurityPolicy(repo=repo, source=None, content=None)


def _owners(repo, present):
    """Build an Owners that is present (any content) or absent."""
    if present:
        return Owners(
            repo=repo,
            source="o/r:OWNERS",
            content="approvers:\n- alice\nreviewers:\n- bob\n",
        )
    return Owners(repo=repo, source=None, content=None)


class AdoptersHealthVisualTests(unittest.TestCase):
    def test_presence_flagged_in_health_visual(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, adopters=_adopters("o/a", True)))
        self.assertTrue(data.health.has_adopters)
        lines = _health_lines(data.health)
        self.assertTrue(any("Adopters: documented" in ln for ln in lines))

    def test_no_adopters_line_when_absent(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, adopters=_adopters("o/a", False)))
        self.assertFalse(data.health.has_adopters)
        lines = _health_lines(data.health)
        self.assertTrue(any("none listed" in ln for ln in lines))

    def test_absent_when_no_adopters_attr(self):
        # A result without any adopters info -> treated as not present.
        data = build_project_slide_data(_result("o/a", HEALTHY, adopters=None))
        self.assertFalse(data.health.has_adopters)

    def test_adopters_folded_into_health_not_separate_visual(self):
        # The slide has exactly the three top visuals; adopters is not a 4th.
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            build_presentation([_result("o/a", HEALTHY, adopters=_adopters("o/a", True))], out)
            prs = Presentation(out)

            def slide_text(slide):
                return "\n".join(
                    s.text_frame.text for s in slide.shapes if s.has_text_frame
                )

            first = slide_text(prs.slides[0])
            # Adopters appears inside the Project health box, with no own heading.
            self.assertIn("Adopters: documented", first)
            # Still exactly the three visual titles.
            self.assertIn("Project health", first)
            self.assertIn("Project direction", first)
            self.assertIn("Top contributors", first)


class SecurityHealthVisualTests(unittest.TestCase):
    def test_presence_flagged_in_health_visual(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, security=_security("o/a", True)))
        self.assertTrue(data.health.has_security_policy)
        lines = _health_lines(data.health)
        self.assertTrue(any("Security policy: documented" in ln for ln in lines))

    def test_absence_shown_in_health_visual(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, security=_security("o/a", False)))
        self.assertFalse(data.health.has_security_policy)
        lines = _health_lines(data.health)
        self.assertTrue(any("Security policy: none found" in ln for ln in lines))

    def test_absent_when_no_security_attr(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, security=None))
        self.assertFalse(data.health.has_security_policy)

    def test_security_folded_into_health_not_separate_visual(self):
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            build_presentation([_result("o/a", HEALTHY, security=_security("o/a", True))], out)
            prs = Presentation(out)

            def slide_text(slide):
                return "\n".join(
                    s.text_frame.text for s in slide.shapes if s.has_text_frame
                )

            first = slide_text(prs.slides[0])
            self.assertIn("Security policy: documented", first)
            # Still exactly the three visual titles (no separate security visual).
            self.assertIn("Project health", first)
            self.assertIn("Project direction", first)
            self.assertIn("Top contributors", first)


class OwnersHealthVisualTests(unittest.TestCase):
    def test_presence_flagged_in_health_visual(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, owners=_owners("o/a", True)))
        self.assertTrue(data.health.has_owners)
        lines = _health_lines(data.health)
        self.assertTrue(any("Owners: documented" in ln for ln in lines))

    def test_absence_shown_in_health_visual(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, owners=_owners("o/a", False)))
        self.assertFalse(data.health.has_owners)
        lines = _health_lines(data.health)
        self.assertTrue(any("Owners: none found" in ln for ln in lines))

    def test_absent_when_no_owners_attr(self):
        data = build_project_slide_data(_result("o/a", HEALTHY, owners=None))
        self.assertFalse(data.health.has_owners)

    def test_owners_folded_into_health_not_separate_visual(self):
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            build_presentation([_result("o/a", HEALTHY, owners=_owners("o/a", True))], out)
            prs = Presentation(out)

            def slide_text(slide):
                return "\n".join(
                    s.text_frame.text for s in slide.shapes if s.has_text_frame
                )

            first = slide_text(prs.slides[0])
            self.assertIn("Owners: documented", first)
            self.assertIn("Project health", first)
            self.assertIn("Project direction", first)
            self.assertIn("Top contributors", first)


class StripMarkdownTests(unittest.TestCase):
    def test_strips_headings_bullets_and_emphasis(self):
        md = "# Title\n\n- **bold** item\n* another `code`\n\n1. ordered\n"
        out = _strip_markdown(md)
        self.assertNotIn("#", out)
        self.assertNotIn("**", out)
        self.assertNotIn("`", out)
        self.assertIn("Title", out)
        self.assertIn("• bold item", out)
        self.assertIn("• another code", out)
        self.assertIn("• ordered", out)

    def test_drops_code_fences_but_keeps_content(self):
        md = "intro\n\n```markdown\nfenced body\n```\n"
        out = _strip_markdown(md)
        self.assertNotIn("```", out)
        self.assertIn("fenced body", out)


class ProjectSlideDataTests(unittest.TestCase):
    def test_derives_all_three_visuals(self):
        data = build_project_slide_data(_result("o/repo", HEALTHY))
        self.assertEqual(data.repo, "o/repo")
        self.assertEqual(data.health.category, HEALTHY)
        self.assertEqual(data.health.commits, 2)
        # Direction is a single sentence drawn from the memo's Direction section.
        self.assertEqual(
            data.direction,
            "The overall trajectory is scheduler reliability hardening.",
        )
        names = {c.name for c in data.contributors}
        self.assertTrue({"alice", "bob"} <= names)
        # The state body is a focused recap: executive summary, risks, and the
        # overall assessment -- not the full memo.
        self.assertIn("Executive summary", data.state_text)
        self.assertIn("A healthy, active scheduler project.", data.state_text)
        self.assertIn("Risks", data.state_text)
        self.assertIn("Bus factor", data.state_text)
        self.assertIn("Overall assessment", data.state_text)
        self.assertIn(
            "A well-run project with a single-maintainer risk.", data.state_text
        )
        # It should NOT reproduce the direction/health section prose verbatim.
        self.assertNotIn("Throughput is high.", data.state_text)

    def test_state_text_override(self):
        data = build_project_slide_data(
            _result("o/repo", HEALTHY), state_text="custom state"
        )
        self.assertEqual(data.state_text, "custom state")


class BuildPresentationTests(unittest.TestCase):
    def test_writes_deck_with_slide_per_project_plus_summary(self):
        results = [_result("o/a", HEALTHY), _result("o/b", ATTENTION)]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            returned = build_presentation(results, out)
            self.assertEqual(returned, out)
            self.assertTrue(os.path.exists(out))

            # Re-open and check structure.
            from pptx import Presentation

            prs = Presentation(out)
            # One slide per project + one overall summary slide.
            self.assertEqual(len(prs.slides), 3)

            def slide_text(slide):
                return "\n".join(
                    shape.text_frame.text
                    for shape in slide.shapes
                    if shape.has_text_frame
                )

            first = slide_text(prs.slides[0])
            self.assertIn("o/a", first)
            self.assertIn("Project health", first)
            self.assertIn("Project direction", first)
            self.assertIn("Top contributors", first)
            self.assertIn("Project state", first)
            # The one-sentence direction appears on the slide.
            self.assertIn("scheduler reliability hardening", first)

            summary = slide_text(prs.slides[2])
            self.assertIn("Overall summary", summary)
            self.assertIn("2 project", summary)
            # Both categories represented in the roll-up.
            self.assertIn("Healthy", summary)
            self.assertIn("Needs attention", summary)

    def test_sections_have_bordered_panels(self):
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            build_presentation([_result("o/a", HEALTHY)], out)
            prs = Presentation(out)

            def panels(slide):
                return [
                    sh
                    for sh in slide.shapes
                    if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                ]

            project_panels = panels(prs.slides[0])
            # Three top visuals + the project-state body each get a panel.
            self.assertEqual(len(project_panels), 4)
            # Panels carry a solid fill and a visible border.
            panel = project_panels[0]
            self.assertIsNotNone(panel.fill.fore_color.rgb)
            self.assertIsNotNone(panel.line.color.rgb)
            self.assertGreater(panel.line.width, 0)

            # The summary slide wraps its body in a panel too.
            self.assertEqual(len(panels(prs.slides[1])), 1)

    def test_single_project_deck_has_two_slides(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "deck.pptx")
            build_presentation([_result("o/only", HEALTHY)], out)
            from pptx import Presentation

            prs = Presentation(out)
            self.assertEqual(len(prs.slides), 2)

    def test_raises_clear_error_when_pptx_missing(self):
        with mock.patch.object(
            presentation, "_require_pptx", side_effect=PptxNotInstalledError("nope")
        ):
            with self.assertRaises(PptxNotInstalledError):
                build_presentation([_result("o/a", HEALTHY)], "/tmp/should-not-write.pptx")


if __name__ == "__main__":
    unittest.main()
