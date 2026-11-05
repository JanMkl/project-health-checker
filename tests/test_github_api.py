import json
import os
import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.github_api import (
    GitHubApiError,
    fetch_list,
    resolve_token,
)

RUN_COMMAND = "github_summary_agent.github_api.run_command"


class ResolveTokenTests(unittest.TestCase):
    def test_explicit_token_wins(self):
        self.assertEqual(resolve_token("explicit"), "explicit")

    @mock.patch.dict(os.environ, {"GITHUB_AUTH_TOKEN": "env-token"}, clear=False)
    def test_falls_back_to_environment(self):
        self.assertEqual(resolve_token(None), "env-token")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_none_when_unset(self):
        self.assertIsNone(resolve_token(None))


class FetchListTests(unittest.TestCase):
    @mock.patch(RUN_COMMAND)
    def test_returns_list_of_dicts(self, mock_run):
        mock_run.return_value = CommandResult(0, json.dumps([{"a": 1}, {"b": 2}]), "")
        data = fetch_list("https://example/x", repo="o/r")
        self.assertEqual(data, [{"a": 1}, {"b": 2}])

    @mock.patch(RUN_COMMAND)
    def test_drops_non_dict_items(self, mock_run):
        mock_run.return_value = CommandResult(0, json.dumps([{"a": 1}, "junk", 7]), "")
        data = fetch_list("https://example/x", repo="o/r")
        self.assertEqual(data, [{"a": 1}])

    @mock.patch(RUN_COMMAND)
    def test_error_object_raises(self, mock_run):
        mock_run.return_value = CommandResult(0, json.dumps({"message": "Not Found"}), "")
        with self.assertRaises(GitHubApiError) as ctx:
            fetch_list("https://example/x", repo="o/r")
        self.assertIn("Not Found", str(ctx.exception))

    @mock.patch(RUN_COMMAND)
    def test_empty_body_is_empty_list(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        self.assertEqual(fetch_list("https://example/x", repo="o/r"), [])


if __name__ == "__main__":
    unittest.main()
