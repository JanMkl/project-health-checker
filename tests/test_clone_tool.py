import os
import tempfile
import unittest
from unittest import mock

from health_checker_agent.clone_tool import (
    clone_or_update,
    latest_commit_hash,
    repo_slug,
)
from health_checker_agent.commands import CommandResult

RUN_COMMAND = "health_checker_agent.clone_tool.run_command"


class RepoSlugTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(repo_slug("metal3-io/metal3-dev-env"), "metal3-io__metal3-dev-env")


class CloneOrUpdateTests(unittest.TestCase):
    @mock.patch(RUN_COMMAND)
    def test_clones_when_absent(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        with tempfile.TemporaryDirectory() as d:
            dest = clone_or_update("octocat/Hello-World", d)
            self.assertEqual(dest, os.path.join(d, "octocat__Hello-World"))
            args = mock_run.call_args_list[0].args[0]
            self.assertEqual(args[0], "git")
            self.assertEqual(args[1], "clone")
            self.assertIn("https://github.com/octocat/Hello-World.git", args)

    @mock.patch(RUN_COMMAND)
    def test_fetches_when_present(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "octocat__Hello-World")
            os.makedirs(os.path.join(dest, ".git"))
            clone_or_update("octocat/Hello-World", d)
            commands = [c.args[0][1] if c.args[0][0] == "git" else "" for c in mock_run.call_args_list]
            # Should fetch (and pull), never clone.
            joined = " ".join(" ".join(c.args[0]) for c in mock_run.call_args_list)
            self.assertIn("fetch", joined)
            self.assertNotIn("clone", joined)


class LatestCommitHashTests(unittest.TestCase):
    @mock.patch(RUN_COMMAND)
    def test_returns_hash(self, mock_run):
        mock_run.return_value = CommandResult(0, "deadbeef\n", "")
        self.assertEqual(latest_commit_hash("/tmp/x"), "deadbeef")

    @mock.patch(RUN_COMMAND)
    def test_empty_on_failure(self, mock_run):
        mock_run.return_value = CommandResult(128, "", "fatal")
        self.assertEqual(latest_commit_hash("/tmp/x"), "")


if __name__ == "__main__":
    unittest.main()
