import unittest
from unittest import mock

from github_summary_agent.__main__ import build_parser, main
from github_summary_agent.git_log_tool import GitLog
from github_summary_agent.issues_tool import OpenIssues


class ParserTests(unittest.TestCase):
    def test_requires_repo_repo_path_since(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_parses_all_args(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "metal3-io/metal3-dev-env",
                "--repo-path",
                "/tmp/metal3-dev-env",
                "--since",
                "30 days ago",
                "--until",
                "2026-11-01",
                "--output-dir",
                "out",
            ]
        )
        self.assertEqual(args.repo, "metal3-io/metal3-dev-env")
        self.assertEqual(args.repo_path, "/tmp/metal3-dev-env")
        self.assertEqual(args.since, "30 days ago")
        self.assertEqual(args.until, "2026-11-01")
        self.assertEqual(args.output_dir, "out")


class MainTests(unittest.TestCase):
    @mock.patch("github_summary_agent.__main__.summarise_project")
    def test_main_invokes_pipeline_and_returns_zero(self, mock_summarise):
        mock_summarise.return_value = mock.Mock(
            memo_path="output/metal3-io__metal3-dev-env-memo.md",
            git_log=GitLog(since="30 days ago", until=None, commits=[]),
            issues=OpenIssues(repo="metal3-io/metal3-dev-env", issues=[]),
        )

        code = main(
            [
                "--repo",
                "metal3-io/metal3-dev-env",
                "--repo-path",
                "/tmp/metal3-dev-env",
                "--since",
                "30 days ago",
            ]
        )

        self.assertEqual(code, 0)
        mock_summarise.assert_called_once_with(
            repo="metal3-io/metal3-dev-env",
            repo_path="/tmp/metal3-dev-env",
            since="30 days ago",
            until=None,
            output_dir="output",
        )


if __name__ == "__main__":
    unittest.main()
