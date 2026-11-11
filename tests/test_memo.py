import unittest
from unittest import mock

from health_checker_agent.commands import CommandResult
from health_checker_agent.git_log_tool import Commit, GitLog
from health_checker_agent.issues_tool import Issue, IssueCollection
from health_checker_agent.memo import build_prompt, generate_memo
from health_checker_agent.pulls_tool import PullRequest, PullRequestCollection


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
        # Prompt requires the explicit one-sentence direction summary marker,
        # which the presentation export relies on.
        self.assertIn("**Direction summary:**", prompt)
        # The memo now also has an Adopters section.
        self.assertIn("## Adopters", prompt)

    def test_build_prompt_includes_adopters_when_present(self):
        from health_checker_agent.adopters_tool import Adopters

        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        adopters = Adopters(
            repo="octocat/Hello-World",
            source="octocat/community:ADOPTERS.md",
            content="# Adopters\n\n| Ericsson | integration |",
        )
        prompt = build_prompt(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
            adopters=adopters,
        )
        self.assertIn("## Adopters", prompt)
        self.assertIn("Ericsson", prompt)
        self.assertIn("octocat/community:ADOPTERS.md", prompt)

    def test_build_prompt_marks_missing_adopters(self):
        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        prompt = build_prompt(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
            adopters=None,
        )
        self.assertIn("## Adopters", prompt)
        self.assertIn("no ADOPTERS file found", prompt)

    @mock.patch("health_checker_agent.memo.run_command")
    def test_generate_memo_defaults_to_kiro_cli(self, mock_run):
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
        # The prompt is fed on stdin (not argv) to avoid ARG_MAX limits.
        self.assertFalse(any("technical program manager" in a for a in args))
        stdin_input = mock_run.call_args.kwargs["stdin_input"]
        self.assertTrue(stdin_input.startswith("You are a technical program manager"))
        self.assertEqual(memo, "# Memo\n\nAll good.")

    @mock.patch("health_checker_agent.memo.run_command")
    def test_generate_memo_uses_codex_backend(self, mock_run):
        # codex returns the memo via --output-last-message, not stdout, so the
        # fake writes the file and returns noisy stdout that must be ignored.
        def fake_run(argv, *, timeout=None, stdin_input=None):
            path = argv[argv.index("--output-last-message") + 1]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# Codex Memo\n\nclean\n")
            return CommandResult(0, "OpenAI Codex v0.0\nframing noise", "")

        mock_run.side_effect = fake_run
        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        memo = generate_memo(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
            backend="codex",
        )
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "codex")
        self.assertIn("exec", args)
        # Prompt still fed on stdin.
        self.assertIsNotNone(mock_run.call_args.kwargs["stdin_input"])
        # The memo comes from the last-message file, not the noisy stdout.
        self.assertEqual(memo, "# Codex Memo\n\nclean")

    @mock.patch("health_checker_agent.memo.run_command")
    def test_generate_memo_uses_cursor_backend(self, mock_run):
        mock_run.return_value = CommandResult(0, "# Memo\n", "")
        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        generate_memo(
            _sample_log(),
            open_issues=open_issues,
            closed_issues=closed_issues,
            open_pulls=open_pulls,
            closed_pulls=closed_pulls,
            backend="cursor-agent",
        )
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "cursor-agent")

    def test_generate_memo_rejects_unknown_backend(self):
        from health_checker_agent.backends import UnknownBackendError

        open_issues, closed_issues, open_pulls, closed_pulls = _sample_activity()
        with self.assertRaises(UnknownBackendError):
            generate_memo(
                _sample_log(),
                open_issues=open_issues,
                closed_issues=closed_issues,
                open_pulls=open_pulls,
                closed_pulls=closed_pulls,
                backend="nope",
            )


if __name__ == "__main__":
    unittest.main()
