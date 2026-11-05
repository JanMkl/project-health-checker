import unittest

from github_summary_agent.fleet import RepoOutcome, build_fleet_report
from github_summary_agent.health import (
    ATTENTION,
    HEALTHY,
    INVESTIGATE,
    HealthAssessment,
)


def _outcome(repo, category, analysed=True):
    return RepoOutcome(
        repo=repo,
        assessment=HealthAssessment(repo, category, f"reason for {repo}"),
        memo_path=f"output/{repo.replace('/', '__')}-memo.md",
        analysed=analysed,
    )


class FleetReportTests(unittest.TestCase):
    def test_groups_by_category_with_counts(self):
        outcomes = [
            _outcome("o/healthy1", HEALTHY),
            _outcome("o/healthy2", HEALTHY),
            _outcome("o/attn", ATTENTION),
            _outcome("o/invest", INVESTIGATE),
        ]
        report = build_fleet_report(outcomes, output_dir="output")

        self.assertIn("# Fleet Health Report", report)
        self.assertIn("Requires management attention (1)", report)
        self.assertIn("Needs investigation / keep an eye on (1)", report)
        self.assertIn("Healthy (no attention needed) (2)", report)
        # Summary line counts.
        self.assertIn("1 requiring attention", report)
        self.assertIn("2 healthy", report)

    def test_attention_section_comes_before_healthy(self):
        outcomes = [_outcome("o/h", HEALTHY), _outcome("o/a", ATTENTION)]
        report = build_fleet_report(outcomes, output_dir="output")
        self.assertLess(
            report.index("Requires management attention"),
            report.index("Healthy (no attention needed)"),
        )

    def test_reused_marker_shown(self):
        outcomes = [_outcome("o/a", ATTENTION, analysed=False)]
        report = build_fleet_report(outcomes, output_dir="output")
        self.assertIn("reused existing memo", report)

    def test_relative_memo_links(self):
        outcomes = [_outcome("o/a", ATTENTION)]
        report = build_fleet_report(outcomes, output_dir="output")
        self.assertIn("(o__a-memo.md)", report)

    def test_empty_bucket_shows_none(self):
        outcomes = [_outcome("o/a", ATTENTION)]
        report = build_fleet_report(outcomes, output_dir="output")
        self.assertIn("_None._", report)


if __name__ == "__main__":
    unittest.main()
