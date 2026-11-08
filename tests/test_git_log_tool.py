import unittest
from unittest import mock

from health_checker_agent.commands import CommandResult
from health_checker_agent.git_log_tool import (
    _REC,
    _SEP,
    GitLog,
    read_git_log,
)


def _make_record(h, name, email, date, subject):
    return _SEP.join([h, name, email, date, subject]) + _REC


class GitLogToolTests(unittest.TestCase):
    @mock.patch("health_checker_agent.git_log_tool.run_command")
    def test_parses_commits(self, mock_run):
        raw = (
            _make_record("abc123def", "Ada", "ada@x.io", "2026-10-01T10:00:00", "Init")
            + _make_record("def456abc", "Lin", "lin@x.io", "2026-10-02T11:00:00", "Fix bug")
        )
        mock_run.return_value = CommandResult(0, raw, "")

        log = read_git_log("/tmp/repo", since="2026-10-01")

        self.assertEqual(log.count, 2)
        self.assertEqual(log.commits[0].author_name, "Ada")
        self.assertEqual(log.commits[1].subject, "Fix bug")

    @mock.patch("health_checker_agent.git_log_tool.run_command")
    def test_passes_since_and_until_args(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        read_git_log("/tmp/repo", since="2026-10-01", until="2026-10-31")

        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "git")
        self.assertIn("--since=2026-10-01", args)
        self.assertIn("--until=2026-10-31", args)
        self.assertIn("/tmp/repo", args)

    @mock.patch("health_checker_agent.git_log_tool.run_command")
    def test_empty_log(self, mock_run):
        mock_run.return_value = CommandResult(0, "", "")
        log = read_git_log("/tmp/repo", since="2026-10-01")
        self.assertEqual(log.count, 0)
        self.assertIn("no commits", log.to_text())

    def test_to_text_includes_header_and_commits(self):
        log = GitLog(since="2026-10-01", until=None, commits=[])
        self.assertIn("Git log since 2026-10-01", log.to_text())


if __name__ == "__main__":
    unittest.main()
