import subprocess
import unittest
from unittest import mock

from github_summary_agent.commands import (
    ALLOWED_COMMANDS,
    CommandNotAllowedError,
    run_command,
)


class RunCommandTests(unittest.TestCase):
    def test_allow_list_contains_expected_commands(self):
        self.assertEqual(ALLOWED_COMMANDS, {"kiro-cli", "git", "curl"})

    def test_rejects_command_not_in_allow_list(self):
        with self.assertRaises(CommandNotAllowedError):
            run_command(["rm", "-rf", "/"])

    def test_rejects_empty_args(self):
        with self.assertRaises(ValueError):
            run_command([])

    @mock.patch("github_summary_agent.commands.subprocess.run")
    def test_runs_allowed_command_and_wraps_result(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "--version"], returncode=0, stdout="git 2.0", stderr=""
        )
        result = run_command(["git", "--version"])
        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "git 2.0")
        mock_run.assert_called_once()

    @mock.patch("github_summary_agent.commands.subprocess.run")
    def test_check_raises_on_nonzero(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "boom"], returncode=1, stdout="", stderr="bad"
        )
        with self.assertRaises(subprocess.CalledProcessError):
            run_command(["git", "boom"], check=True)

    @mock.patch("github_summary_agent.commands.subprocess.run")
    def test_check_false_returns_failed_result(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl", "x"], returncode=22, stdout="", stderr="404"
        )
        result = run_command(["curl", "x"], check=False)
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 22)

    @mock.patch("github_summary_agent.commands.subprocess.run")
    def test_stdin_input_passed_to_subprocess(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["kiro-cli", "chat"], returncode=0, stdout="ok", stderr=""
        )
        run_command(["kiro-cli", "chat"], stdin_input="a big prompt")
        self.assertEqual(mock_run.call_args.kwargs["input"], "a big prompt")


if __name__ == "__main__":
    unittest.main()
