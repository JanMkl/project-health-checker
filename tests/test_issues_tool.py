import json
import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.issues_tool import read_open_issues


class IssuesToolTests(unittest.TestCase):
    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_parses_issues_and_skips_pull_requests(self, mock_run):
        payload = [
            {
                "number": 1,
                "title": "Add dark mode",
                "user": {"login": "ada"},
                "created_at": "2026-10-01T00:00:00Z",
                "labels": [{"name": "enhancement"}],
                "comments": 3,
            },
            {
                "number": 2,
                "title": "A pull request",
                "user": {"login": "lin"},
                "created_at": "2026-10-02T00:00:00Z",
                "labels": [],
                "comments": 0,
                "pull_request": {"url": "x"},
            },
        ]
        mock_run.return_value = CommandResult(0, json.dumps(payload), "")

        issues = read_open_issues("octocat/Hello-World")

        self.assertEqual(issues.count, 1)
        self.assertEqual(issues.issues[0].number, 1)
        self.assertEqual(issues.issues[0].author, "ada")
        self.assertIn("enhancement", issues.issues[0].labels)

    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_uses_curl_with_state_open(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_open_issues("octocat/Hello-World")

        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "curl")
        url = args[-1]
        self.assertIn("/repos/octocat/Hello-World/issues", url)
        self.assertIn("state=open", url)

    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_empty_issues(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        issues = read_open_issues("octocat/Hello-World")
        self.assertEqual(issues.count, 0)
        self.assertIn("no open issues", issues.to_text())


if __name__ == "__main__":
    unittest.main()
