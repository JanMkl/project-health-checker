import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.git_log_tool import Commit, GitLog
from github_summary_agent.issues_tool import Issue, OpenIssues
from github_summary_agent.memo import build_prompt, generate_memo


def _sample_log():
    return GitLog(
        since="2026-10-01",
        until=None,
        commits=[Commit("abc12345", "Ada", "ada@x.io", "2026-10-01T10:00:00", "Init")],
    )


def _sample_issues():
    return OpenIssues(
        repo="octocat/Hello-World",
        issues=[Issue(1, "Add dark mode", "ada", "2026-10-01T00:00:00Z", ["enhancement"], 3)],
    )


class MemoTests(unittest.TestCase):
    def test_build_prompt_includes_log_and_issues(self):
        prompt = build_prompt(_sample_log(), _sample_issues())
        self.assertIn("## Git activity", prompt)
        self.assertIn("## Open issues", prompt)
        self.assertIn("Ada", prompt)
        self.assertIn("Add dark mode", prompt)
        self.assertIn("Markdown", prompt)

    @mock.patch("github_summary_agent.memo.run_command")
    def test_generate_memo_calls_kiro_cli(self, mock_run):
        mock_run.return_value = CommandResult(0, "# Memo\n\nAll good.\n", "")
        memo = generate_memo(_sample_log(), _sample_issues())

        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "kiro-cli")
        self.assertEqual(args[1], "chat")
        self.assertIn("--no-interactive", args)
        # The prompt is passed as the positional INPUT argument.
        self.assertTrue(args[-1].startswith("You are a technical program manager"))
        self.assertEqual(memo, "# Memo\n\nAll good.")


if __name__ == "__main__":
    unittest.main()
