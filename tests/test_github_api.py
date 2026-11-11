import base64
import json
import os
import subprocess
import unittest
from unittest import mock

from health_checker_agent.commands import CommandResult
from health_checker_agent.github_api import (
    GitHubApiError,
    fetch_list,
    fetch_text,
    resolve_token,
)

RUN_COMMAND = "health_checker_agent.github_api.run_command"


def _contents_response(text: str) -> str:
    """Build a GitHub contents-API JSON body with base64-encoded content."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return json.dumps({"encoding": "base64", "content": encoded})


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

    @mock.patch(RUN_COMMAND)
    def test_curl_failure_does_not_leak_token(self, mock_run):
        # The failing command's argv carries the Authorization header with the
        # token; the raised error must not expose it.
        argv = [
            "curl",
            "--header",
            "Authorization: Bearer github_pat_SUPERSECRET",
            "https://api.github.com/repos/o/r/pulls",
        ]
        mock_run.side_effect = subprocess.CalledProcessError(22, argv, "", "")
        with self.assertRaises(GitHubApiError) as ctx:
            fetch_list(
                "https://api.github.com/repos/o/r/pulls",
                repo="o/r",
                token="github_pat_SUPERSECRET",
            )
        msg = str(ctx.exception)
        self.assertNotIn("github_pat_SUPERSECRET", msg)
        self.assertNotIn("Bearer", msg)
        self.assertIn("o/r", msg)
        self.assertIn("22", msg)


class FetchTextTests(unittest.TestCase):
    @mock.patch(RUN_COMMAND)
    def test_decodes_base64_content(self, mock_run):
        mock_run.return_value = CommandResult(0, _contents_response("# Adopters\nEricsson"), "")
        self.assertEqual(fetch_text("https://example/x"), "# Adopters\nEricsson")

    @mock.patch(RUN_COMMAND)
    def test_runs_without_fail_flag(self, mock_run):
        # fetch_text omits --fail so a 404 body can be inspected (returns None),
        # and uses check=False so a non-zero exit is not an exception.
        mock_run.return_value = CommandResult(0, _contents_response("x"), "")
        fetch_text("https://example/x")
        argv = mock_run.call_args.args[0]
        self.assertNotIn("--fail", argv)
        self.assertFalse(mock_run.call_args.kwargs["check"])

    @mock.patch(RUN_COMMAND)
    def test_missing_file_returns_none(self, mock_run):
        # A 404 from the contents API is a JSON error object, not a file.
        mock_run.return_value = CommandResult(0, json.dumps({"message": "Not Found"}), "")
        self.assertIsNone(fetch_text("https://example/x"))

    @mock.patch(RUN_COMMAND)
    def test_empty_body_returns_none(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        self.assertIsNone(fetch_text("https://example/x"))

    @mock.patch(RUN_COMMAND)
    def test_invalid_json_returns_none(self, mock_run):
        mock_run.return_value = CommandResult(0, "not json", "")
        self.assertIsNone(fetch_text("https://example/x"))

    @mock.patch(RUN_COMMAND, side_effect=OSError("boom"))
    def test_subprocess_error_returns_none(self, _mock_run):
        self.assertIsNone(fetch_text("https://example/x"))


if __name__ == "__main__":
    unittest.main()
