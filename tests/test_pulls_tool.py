import json
import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.pulls_tool import read_pull_requests

RUN_COMMAND = "github_summary_agent.github_api.run_command"


class PullsToolTests(unittest.TestCase):
    @mock.patch(RUN_COMMAND)
    def test_parses_pull_requests(self, mock_run):
        payload = [
            {
                "number": 10,
                "title": "Add CI",
                "user": {"login": "ada"},
                "created_at": "2026-10-01T00:00:00Z",
                "state": "open",
                "merged_at": None,
            },
            {
                "number": 11,
                "title": "Fix flake",
                "user": {"login": "lin"},
                "created_at": "2026-09-01T00:00:00Z",
                "state": "closed",
                "merged_at": "2026-09-02T00:00:00Z",
            },
        ]
        mock_run.return_value = CommandResult(0, json.dumps(payload), "")

        pulls = read_pull_requests("octocat/Hello-World", state="all")

        self.assertEqual(pulls.count, 2)
        self.assertEqual(pulls.pulls[0].author, "ada")
        self.assertFalse(pulls.pulls[0].merged)
        self.assertTrue(pulls.pulls[1].merged)

    @mock.patch(RUN_COMMAND)
    def test_uses_pulls_endpoint_with_state(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        read_pull_requests("octocat/Hello-World", state="closed")

        url = mock_run.call_args.args[0][-1]
        self.assertIn("/repos/octocat/Hello-World/pulls", url)
        self.assertIn("state=closed", url)

    @mock.patch(RUN_COMMAND)
    def test_merged_pr_renders_as_merged(self, mock_run):
        payload = [
            {
                "number": 11,
                "title": "Fix flake",
                "user": {"login": "lin"},
                "created_at": "2026-09-01T00:00:00Z",
                "state": "closed",
                "merged_at": "2026-09-02T00:00:00Z",
            }
        ]
        mock_run.return_value = CommandResult(0, json.dumps(payload), "")
        pulls = read_pull_requests("octocat/Hello-World", state="closed")
        text = pulls.to_text()
        self.assertIn("merged", text)
        self.assertIn("by lin", text)

    @mock.patch(RUN_COMMAND)
    def test_empty_pulls(self, mock_run):
        mock_run.return_value = CommandResult(0, "[]", "")
        pulls = read_pull_requests("octocat/Hello-World")
        self.assertEqual(pulls.count, 0)
        self.assertIn("no open pull requests", pulls.to_text())


if __name__ == "__main__":
    unittest.main()
