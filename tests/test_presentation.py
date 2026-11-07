import os
import tempfile
import unittest
from dataclasses import dataclass
from typing import List
from unittest import mock

from github_summary_agent import presentation
from github_summary_agent.git_log_tool import Commit, GitLog
from github_summary_agent.health import ATTENTION, HEALTHY, HealthAssessment
from github_summary_agent.issues_tool import Issue, IssueCollection
from github_summary_agent.presentation import (
    PptxNotInstalledError,
    _strip_markdown,
    build_presentation,
    build_project_slide_data,
)
from github_summary_agent.pulls_tool import PullRequest, PullRequestCollection


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


def _result(repo, category, *, commits=2, memo=_DEFAULT_MEMO):
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
    )


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
