import unittest
from unittest import mock

from github_summary_agent.commands import CommandResult
from github_summary_agent.git_log_tool import Commit, GitLog
from github_summary_agent.issues_tool import Issue, IssueCollection
from github_summary_agent.memo import build_prompt, generate_memo
from github_summary_agent.pulls_tool import PullRequest, PullRequestCollection


def _sample_log():
    return GitLog(
        since="2026-10-01",
        until=None,
        commits=[Commit("abc12345", "Ada", "ada@x.io", "2026-10-01T10:00:00", "Init")],
    )


def _sample_activity():
    open_issues = IssueCollection(
        repo="octocat/Hello-World",
        state="open",
        issues=[
            Issue(1, "Add dark mode", "ada", "2026-10-01T00:00:00Z", "open", ["enhancement"], 3)
        ],
    )
    closed_issues = IssueCollection(
        repo="octocat/Hello-World",
        state="closed",
        issues=[Issue(2, "Old bug", "lin", "2026-08-01T00:00:00Z", "closed", [], 1)],
    )
    open_pulls = PullRequestCollection(
        repo="octocat/Hello-World",
        state="open",
        pulls=[PullRequest(10, "Add CI", "mara", "2026-10-02T00:00:00Z", "open", False)],
    )
    closed_pulls = PullRequestCollection(
        repo="octocat/Hello-World",
        state="closed",
        pulls=[PullRequest(11, "Fix flake", "ravi", "2026-09-01T00:00:00Z", "closed", True)],
    )
    return open_issues, closed_issues, open_pulls, closed_pulls


class MemoTests(unittest.TestCase):
    def test_build_prompt_includes_all_activity_sections(self):
        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        prompt = build_prompt(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
        )
        self.assertIn("## Git activity", prompt)
        self.assertIn("## Open issues", prompt)
        self.assertIn("## Closed issues", prompt)
        self.assertIn("## Open pull requests", prompt)
        self.assertIn("## Closed pull requests", prompt)
        # Contributors from issues and PRs appear in the prompt.
        self.assertIn("ada", prompt)
        self.assertIn("mara", prompt)
        self.assertIn("ravi", prompt)
        # Prompt instructs not to rely on commits alone.
        self.assertIn("commit authorship alone", prompt)

    @mock.patch("github_summary_agent.memo.run_command")
    def test_generate_memo_calls_kiro_cli(self, mock_run):
        mock_run.return_value = CommandResult(0, "# Memo\n\nAll good.\n", "")
        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        memo = generate_memo(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
        )

        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "kiro-cli")
        self.assertEqual(args[1], "chat")
        self.assertIn("--no-interactive", args)
        self.assertTrue(args[-1].startswith("You are a technical program manager"))
        self.assertEqual(memo, "# Memo\n\nAll good.")


if __name__ == "__main__":
    unittest.main()
