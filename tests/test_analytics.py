import unittest

from github_summary_agent.analytics import (
    Contributor,
    health_metrics,
    is_bot,
    project_direction,
    project_state_summary,
    top_contributors,
)
from github_summary_agent.git_log_tool import Commit, GitLog
from github_summary_agent.issues_tool import Issue, IssueCollection
from github_summary_agent.pulls_tool import PullRequest, PullRequestCollection


def _log(subjects=(), authors=None):
    authors = authors or ["alice"] * len(subjects)
    commits = [
        Commit(f"h{i}", authors[i], f"{authors[i]}@x", "2026-10-01", subjects[i])
        for i in range(len(subjects))
    ]
    return GitLog(since="x", until=None, commits=commits)


def _issues(state, items):
    # items: list of (title, author)
    issues = [
        Issue(number=i, title=t, author=a, created_at="2026-10-01", state=state)
        for i, (t, a) in enumerate(items)
    ]
    return IssueCollection(repo="o/r", state=state, issues=issues)


def _pulls(state, items):
    # items: list of (title, author)
    pulls = [
        PullRequest(number=i, title=t, author=a, created_at="2026-10-01", state=state)
        for i, (t, a) in enumerate(items)
    ]
    return PullRequestCollection(repo="o/r", state=state, pulls=pulls)


class HealthMetricsTests(unittest.TestCase):
    def test_bundles_counts_and_derived_totals(self):
        m = health_metrics(
            "healthy",
            "looks good",
            _log(["a", "b", "c"]),
            _issues("open", [("i1", "x"), ("i2", "y")]),
            _issues("closed", [("i3", "z")]),
            _pulls("open", [("p1", "x")]),
            _pulls("closed", [("p2", "y"), ("p3", "z")]),
        )
        self.assertEqual(m.category, "healthy")
        self.assertEqual(m.reason, "looks good")
        self.assertEqual(m.commits, 3)
        self.assertEqual(m.open_issues, 2)
        self.assertEqual(m.closed_issues, 1)
        self.assertEqual(m.open_pulls, 1)
        self.assertEqual(m.closed_pulls, 2)
        self.assertEqual(m.open_work, 3)
        self.assertEqual(m.closed_work, 3)


class TopContributorsTests(unittest.TestCase):
    def test_ranks_by_combined_activity(self):
        contributors = top_contributors(
            _log(["c1", "c2"], authors=["alice", "alice"]),
            _issues("open", [("i", "bob")]),
            _issues("closed", []),
            _pulls("open", [("p", "bob")]),
            _pulls("closed", [("p2", "bob")]),
        )
        # alice: 2 commits = 2; bob: 1 issue + 2 pulls = 3 -> bob first.
        self.assertEqual(contributors[0].name, "bob")
        self.assertEqual(contributors[0].total, 3)
        self.assertEqual(contributors[1].name, "alice")
        self.assertEqual(contributors[1].commits, 2)

    def test_folds_in_issue_and_pr_only_contributors(self):
        # A community member with no commits should still surface.
        contributors = top_contributors(
            _log(["c"], authors=["alice"]),
            _issues("open", [("i", "carol")]),
            _issues("closed", [("i2", "carol")]),
            _pulls("open", []),
            _pulls("closed", []),
        )
        names = {c.name for c in contributors}
        self.assertIn("carol", names)
        carol = next(c for c in contributors if c.name == "carol")
        self.assertEqual(carol.commits, 0)
        self.assertEqual(carol.issues, 2)

    def test_skips_unknown_authors(self):
        contributors = top_contributors(
            _log(["c"], authors=["unknown"]),
            _issues("open", [("i", "")]),
            _issues("closed", []),
            _pulls("open", []),
            _pulls("closed", []),
        )
        self.assertEqual(contributors, [])

    def test_merges_case_variants(self):
        contributors = top_contributors(
            _log(["a", "b"], authors=["Alice", "alice"]),
            _issues("open", []),
            _issues("closed", []),
            _pulls("open", []),
            _pulls("closed", []),
        )
        self.assertEqual(len(contributors), 1)
        self.assertEqual(contributors[0].commits, 2)

    def test_respects_limit(self):
        authors = [f"dev{i}" for i in range(10)]
        contributors = top_contributors(
            _log(["c"] * 10, authors=authors),
            _issues("open", []),
            _issues("closed", []),
            _pulls("open", []),
            _pulls("closed", []),
            limit=3,
        )
        self.assertEqual(len(contributors), 3)

    def test_excludes_bot_accounts(self):
        contributors = top_contributors(
            _log(
                ["c1", "c2", "c3"],
                authors=["dependabot[bot]", "kubernetes-prow[bot]", "alice"],
            ),
            _issues("open", [("i", "renovate[bot]")]),
            _issues("closed", []),
            _pulls("open", [("p", "github-actions[bot]")]),
            _pulls("closed", []),
        )
        names = {c.name for c in contributors}
        self.assertEqual(names, {"alice"})

    def test_bot_only_activity_yields_no_contributors(self):
        contributors = top_contributors(
            _log(["c"], authors=["k8s-ci-robot"]),
            _issues("open", [("i", "dependabot[bot]")]),
            _issues("closed", []),
            _pulls("open", []),
            _pulls("closed", []),
        )
        self.assertEqual(contributors, [])


class IsBotTests(unittest.TestCase):
    def test_detects_bot_suffix(self):
        self.assertTrue(is_bot("kubernetes-prow[bot]"))
        self.assertTrue(is_bot("dependabot[bot]"))
        self.assertTrue(is_bot("github-actions[bot]"))

    def test_detects_known_automation_accounts(self):
        self.assertTrue(is_bot("k8s-ci-robot"))
        self.assertTrue(is_bot("web-flow"))
        self.assertTrue(is_bot("dependabot"))

    def test_detects_bot_word_segment(self):
        self.assertTrue(is_bot("renovate-bot"))
        self.assertTrue(is_bot("some_bot_account"))

    def test_humans_are_not_bots(self):
        for name in ("Camila Macedo", "alice", "dongjiang", "Abbott", "Botticelli"):
            self.assertFalse(is_bot(name), name)

    def test_empty_is_not_a_bot(self):
        self.assertFalse(is_bot(""))
        self.assertFalse(is_bot("   "))


class ProjectDirectionTests(unittest.TestCase):
    def test_uses_explicit_direction_summary_marker(self):
        memo = (
            "# Memo\n\n"
            "## Project Direction\n"
            "Recent activity points to themes:\n"
            "- **Reliability.** work.\n"
            "- **Performance.** work.\n\n"
            "**Direction summary:** The project is in a maturity-focused phase, "
            "prioritising stability and security over new features.\n\n"
            "## Project Health\nFine.\n"
        )
        self.assertEqual(
            project_direction(memo),
            "The project is in a maturity-focused phase, prioritising "
            "stability and security over new features.",
        )

    def test_marker_without_bold_is_recognised(self):
        memo = (
            "## Project Direction\n"
            "- **X.** detail.\n"
            "Direction summary: The team is consolidating infrastructure.\n"
        )
        self.assertEqual(
            project_direction(memo),
            "The team is consolidating infrastructure.",
        )

    def test_marker_takes_precedence_over_heuristics(self):
        # Both a trailing trajectory line and the marker are present; the
        # explicit marker must win.
        memo = (
            "## Project Direction\n"
            "- **X.** detail.\n"
            "The overall trajectory is heuristic text that should lose.\n"
            "**Direction summary:** The explicit summary wins.\n"
        )
        self.assertEqual(
            project_direction(memo), "The explicit summary wins."
        )

    def test_prefers_closing_trajectory_sentence(self):
        memo = (
            "# Memo\n\n"
            "## Project Direction\n"
            "Recent activity points to two themes:\n"
            "- **Reliability hardening.** Lots of fixes.\n"
            "- **Performance.** Faster paths.\n"
            "The overall trajectory is a product being hardened for "
            "production scale, not rapid feature growth.\n\n"
            "## Project Health\nFine.\n"
        )
        d = project_direction(memo)
        self.assertEqual(
            d,
            "The overall trajectory is a product being hardened for "
            "production scale, not rapid feature growth.",
        )

    def test_returns_single_sentence_only(self):
        memo = (
            "## Project Direction\n"
            "- **X.** detail.\n"
            "The net direction is sustaining mode. A second sentence here.\n"
        )
        d = project_direction(memo)
        self.assertEqual(d, "The net direction is sustaining mode.")

    def test_synthesises_sentence_from_bullet_themes(self):
        memo = (
            "## Direction of the Project\n"
            "Recent activity points to three clear themes:\n"
            "- **Helm plugin hardening (primary focus).** text.\n"
            "- **Release readiness for the Go scaffold.** text.\n"
            "- **Supply-chain and CI security.** text.\n"
        )
        d = project_direction(memo)
        self.assertTrue(d.startswith("The project is focused on "))
        self.assertIn("helm plugin hardening", d)
        self.assertIn("release readiness for the Go scaffold", d)
        self.assertIn("supply-chain and CI security", d)
        # The "(primary focus)" qualifier is dropped.
        self.assertNotIn("primary focus", d)
        self.assertTrue(d.endswith("."))

    def test_handles_bolded_paragraph_themes_with_enumerators(self):
        memo = (
            "## Project Direction\n"
            "Three clear themes emerge from recent activity:\n\n"
            "**1. A major PowerVS API modernization.** text.\n\n"
            "**2. Expanding networking capability.** text.\n"
        )
        d = project_direction(memo)
        self.assertTrue(d.startswith("The project is focused on "))
        # Enumerator stripped; acronym preserved.
        self.assertIn("a major PowerVS API modernization", d)
        self.assertNotIn("1.", d)

    def test_preserves_acronyms_in_themes(self):
        memo = (
            "## Project Direction\n"
            "themes:\n"
            "- **API modernization.** text.\n"
            "- **CLI usability and kubectl parity.** text.\n"
        )
        d = project_direction(memo)
        self.assertIn("API modernization", d)
        self.assertIn("CLI usability and kubectl parity", d)

    def test_does_not_mistake_intro_line_for_summary(self):
        # The intro precedes the themes and must not be returned as the summary.
        memo = (
            "## Project Direction\n"
            "Three themes define where the project is heading.\n"
            "- **UI modernization.** text.\n"
            "- **Security.** text.\n"
        )
        d = project_direction(memo)
        self.assertTrue(d.startswith("The project is focused on "))
        self.assertIn("UI modernization", d)
        self.assertNotIn("define where the project is heading", d)

    def test_falls_back_to_executive_summary(self):
        memo = (
            "# Memo\n\n"
            "## Executive Summary\n"
            "The project is highly active and healthy. More detail follows.\n\n"
            "## Project Health\nFine.\n"
        )
        d = project_direction(memo)
        self.assertEqual(d, "The project is highly active and healthy.")

    def test_empty_when_no_direction_or_summary(self):
        self.assertEqual(project_direction(""), "")
        self.assertEqual(
            project_direction("## Project Health\nAll good.\n"), ""
        )

    def test_truncates_overly_long_sentence(self):
        long_tail = "word " * 100
        memo = (
            "## Project Direction\n"
            "- **X.** d.\n"
            f"The direction is {long_tail}and more.\n"
        )
        d = project_direction(memo, max_chars=60)
        self.assertLessEqual(len(d), 61)
        self.assertTrue(d.endswith("…"))


_STRUCTURED_MEMO = (
    "# Acme\n\n"
    "## Executive Summary\n"
    "Acme is a healthy, actively maintained project with strong throughput.\n\n"
    "## Project Direction\n"
    "- **Stability.** work.\n"
    "**Direction summary:** The project is maturing.\n\n"
    "## Active Contributors and Community Members\n- Alice\n\n"
    "## Project Health\n"
    "Activity is high and responsiveness strong.\n\n"
    "## Risks\n"
    "- **Key-person concentration.** A single maintainer authors most work. "
    "Broadening reviewers would help.\n"
    "- **Alpha surface.** Several alpha plugins are stabilising at once.\n\n"
    "**Overall assessment:** A well-run project whose main action is reducing "
    "reliance on its lead maintainer.\n"
)


class ProjectStateSummaryTests(unittest.TestCase):
    def test_includes_exec_risks_and_overall_in_order(self):
        out = project_state_summary(_STRUCTURED_MEMO)
        self.assertIn("Executive summary", out)
        self.assertIn("Acme is a healthy", out)
        self.assertIn("Risks", out)
        self.assertIn("Key-person concentration", out)
        self.assertIn("Overall assessment", out)
        self.assertIn("A well-run project", out)
        # Order: exec < risks < overall.
        self.assertLess(out.index("Executive summary"), out.index("Risks"))
        self.assertLess(out.index("Risks"), out.index("Overall assessment"))

    def test_omits_direction_and_health_body(self):
        out = project_state_summary(_STRUCTURED_MEMO)
        # The direction summary and health prose belong to the top visuals and
        # the Project Health section; they must not be duplicated here.
        self.assertNotIn("The project is maturing", out)
        self.assertNotIn("Activity is high and responsiveness strong", out)

    def test_risks_shortened_to_label_plus_first_sentence(self):
        out = project_state_summary(_STRUCTURED_MEMO)
        # The long key-person bullet is trimmed to its lead-in + first sentence.
        self.assertIn("Key-person concentration: A single maintainer authors most work.", out)
        self.assertNotIn("Broadening reviewers would help", out)

    def test_strips_inline_markdown(self):
        memo = (
            "## Executive Summary\n"
            "A project focused on **security** and `tooling` upkeep.\n\n"
            "## Risks\n- **X.** a risk.\n\n"
            "**Overall assessment:** All **good** here.\n"
        )
        out = project_state_summary(memo)
        self.assertNotIn("**", out)
        self.assertNotIn("`", out)
        self.assertIn("security and tooling upkeep", out)

    def test_fallback_risks_subblock_without_risks_heading(self):
        # Older memos put risks under a bold "**Risks:**" label inside Health.
        memo = (
            "## Executive Summary\nHealthy project.\n\n"
            "## Project Health\n"
            "Active and responsive.\n\n"
            "**Risks:**\n"
            "- **Bus factor.** One maintainer does most work.\n"
            "- **Backlog.** Old issues piling up.\n\n"
            "Overall, the project is solid but concentrated.\n"
        )
        out = project_state_summary(memo)
        self.assertIn("Bus factor", out)
        self.assertIn("Backlog", out)
        # Overall assessment falls back to the health section's closing line.
        self.assertIn("Overall assessment", out)
        self.assertIn("the project is solid but concentrated", out)

    def test_empty_for_unstructured_memo(self):
        self.assertEqual(project_state_summary(""), "")
        self.assertEqual(project_state_summary("just some prose, no headings"), "")


if __name__ == "__main__":
    unittest.main()
