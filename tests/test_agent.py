import os
import tempfile
import unittest
from unittest import mock

from github_summary_agent.agent import (
    _resolve_output_path,
    _slugify,
    summarise_project,
)
from github_summary_agent.git_log_tool import GitLog
from github_summary_agent.issues_tool import OpenIssues


class HelperTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(_slugify("octocat/Hello-World"), "octocat__Hello-World")

    def test_resolve_output_path_ok(self):
        with tempfile.TemporaryDirectory() as d:
            path = _resolve_output_path(d, "memo.md")
            self.assertTrue(path.startswith(os.path.abspath(d)))

    def test_resolve_output_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                _resolve_output_path(d, "../escape.md")


class SummariseProjectTests(unittest.TestCase):
    @mock.patch("github_summary_agent.agent.generate_memo")
    @mock.patch("github_summary_agent.agent.read_open_issues")
    @mock.patch("github_summary_agent.agent.read_git_log")
    def test_pipeline_writes_memo_to_output(self, mock_log, mock_issues, mock_memo):
        mock_log.return_value = GitLog(since="2026-10-01", until=None, commits=[])
        mock_issues.return_value = OpenIssues(repo="octocat/Hello-World", issues=[])
        mock_memo.return_value = "# Memo\n\nContent."

        with tempfile.TemporaryDirectory() as d:
            result = summarise_project(
                "octocat/Hello-World",
                "/tmp/repo",
                since="2026-10-01",
                output_dir=d,
            )

            self.assertTrue(os.path.exists(result.memo_path))
            with open(result.memo_path, encoding="utf-8") as fh:
                written = fh.read()
            self.assertEqual(written, "# Memo\n\nContent.\n")
            self.assertEqual(result.repo, "octocat/Hello-World")
            mock_log.assert_called_once()
            mock_issues.assert_called_once_with("octocat/Hello-World")
            mock_memo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
