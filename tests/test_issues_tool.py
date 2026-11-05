import json
import os
import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.issues_tool import (
    GitHubApiError,
    read_open_issues,
)


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
    def test_follows_redirects(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_open_issues("octocat/Hello-World")

        args = mock_run.call_args.args[0]
        self.assertIn("--location", args)

    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_api_error_object_raises(self, mock_run):
        # GitHub returns a JSON object (not a list) on error, e.g. a 301 body.
        mock_run.return_value = CommandResult(
            0, json.dumps({"message": "Moved Permanently"}), ""
        )
        with self.assertRaises(GitHubApiError) as ctx:
            read_open_issues("metal3-io/metal3-ipam")
        self.assertIn("Moved Permanently", str(ctx.exception))

    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_empty_issues(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        issues = read_open_issues("octocat/Hello-World")
        self.assertEqual(issues.count, 0)
        self.assertIn("no open issues", issues.to_text())

    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_explicit_token_adds_auth_header(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_open_issues("octocat/Hello-World", token="secret-token")

        args = mock_run.call_args.args[0]
        self.assertIn("Authorization: Bearer secret-token", args)

    @mock.patch.dict(os.environ, {"GITHUB_AUTH_TOKEN": "env-token"}, clear=False)
    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_token_read_from_environment(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_open_issues("octocat/Hello-World")

        args = mock_run.call_args.args[0]
        self.assertIn("Authorization: Bearer env-token", args)

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("github_summary_agent.issues_tool.run_command")
    def test_no_token_means_no_auth_header(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_open_issues("octocat/Hello-World")

        args = mock_run.call_args.args[0]
        self.assertFalse(any("Authorization" in a for a in args))


if __name__ == "__main__":
    unittest.main()
