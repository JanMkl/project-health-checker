import os
import tempfile
import unittest
from unittest import mock

from health_checker_agent import agent
from health_checker_agent.agent import (
    _resolve_output_path,
    _slugify,
    run_fleet,
    run_repo,
)
from health_checker_agent.config import Config
from health_checker_agent.git_log_tool import Commit, GitLog
from health_checker_agent.issues_tool import Issue, IssueCollection
from health_checker_agent.pulls_tool import PullRequestCollection


def _log(n=1):
    return GitLog(
        since="x",
        until=None,
        commits=[Commit(f"h{i}", "a", "a@x", "d", "m") for i in range(n)],
    )


def _issues(state, n=0):
    return IssueCollection(
        repo="o/r",
        state=state,
        issues=[Issue(i, "t", "u", "d", state) for i in range(n)],
    )


def _pulls(state, n=0):
    return PullRequestCollection(repo="o/r", state=state, pulls=[])


class HelperTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(_slugify("octocat/Hello-World"), "octocat__Hello-World")

    def test_resolve_output_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                _resolve_output_path(d, "../escape.md")


class RunRepoTests(unittest.TestCase):
    def _patches(self, stack, *, clone_dest, log, open_i, closed_i, open_p, closed_p, memo):
        stack.enter_context(mock.patch.object(agent, "clone_or_update", return_value=clone_dest))
        stack.enter_context(mock.patch.object(agent, "read_git_log", return_value=log))
        stack.enter_context(
            mock.patch.object(
                agent,
                "read_issues",
                side_effect=lambda repo, *, state, token: open_i if state == "open" else closed_i,
            )
        )
        stack.enter_context(
            mock.patch.object(
                agent,
                "read_pull_requests",
                side_effect=lambda repo, *, state, token: open_p if state == "open" else closed_p,
            )
        )
        return stack.enter_context(mock.patch.object(agent, "generate_memo", return_value=memo))

    def test_first_run_analyses_and_writes_memo(self):
        import contextlib

        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            mock_memo = self._patches(
                stack,
                clone_dest="/tmp/clone",
                log=_log(3),
                open_i=_issues("open", 1),
                closed_i=_issues("closed", 2),
                open_p=_pulls("open"),
                closed_p=_pulls("closed"),
                memo="# Memo\n\nBody.",
            )
            result = run_repo("o/r", since="x", work_dir=os.path.join(d, "repos"), output_dir=d)

            self.assertTrue(result.analysed)
            self.assertTrue(os.path.exists(result.memo_path))
            mock_memo.assert_called_once()

    def test_second_run_reuses_memo_when_unchanged(self):
        import contextlib

        with tempfile.TemporaryDirectory() as d:
            # First run writes memo + state.
            with contextlib.ExitStack() as stack:
                self._patches(
                    stack,
                    clone_dest="/tmp/clone",
                    log=_log(3),
                    open_i=_issues("open", 1),
                    closed_i=_issues("closed", 2),
                    open_p=_pulls("open"),
                    closed_p=_pulls("closed"),
                    memo="# Memo\n\nBody.",
                )
                run_repo("o/r", since="x", work_dir=os.path.join(d, "repos"), output_dir=d)

            # Second run with identical inputs should NOT call generate_memo.
            with contextlib.ExitStack() as stack:
                mock_memo = self._patches(
                    stack,
                    clone_dest="/tmp/clone",
                    log=_log(3),
                    open_i=_issues("open", 1),
                    closed_i=_issues("closed", 2),
                    open_p=_pulls("open"),
                    closed_p=_pulls("closed"),
                    memo="SHOULD NOT BE USED",
                )
                result = run_repo("o/r", since="x", work_dir=os.path.join(d, "repos"), output_dir=d)
                self.assertFalse(result.analysed)
                mock_memo.assert_not_called()

    def test_force_reanalyses_even_when_unchanged(self):
        import contextlib

        with tempfile.TemporaryDirectory() as d:
            for _ in range(1):
                with contextlib.ExitStack() as stack:
                    self._patches(
                        stack,
                        clone_dest="/tmp/clone",
                        log=_log(3),
                        open_i=_issues("open", 1),
                        closed_i=_issues("closed", 2),
                        open_p=_pulls("open"),
                        closed_p=_pulls("closed"),
                        memo="# Memo",
                    )
                    run_repo("o/r", since="x", work_dir=os.path.join(d, "repos"), output_dir=d)

            with contextlib.ExitStack() as stack:
                mock_memo = self._patches(
                    stack,
                    clone_dest="/tmp/clone",
                    log=_log(3),
                    open_i=_issues("open", 1),
                    closed_i=_issues("closed", 2),
                    open_p=_pulls("open"),
                    closed_p=_pulls("closed"),
                    memo="# Memo",
                )
                result = run_repo(
                    "o/r", since="x", work_dir=os.path.join(d, "repos"), output_dir=d, force=True
                )
                self.assertTrue(result.analysed)
                mock_memo.assert_called_once()


class RunFleetTests(unittest.TestCase):
    def test_runs_each_repo_and_writes_report(self):
        with tempfile.TemporaryDirectory() as d:
            fake_result = mock.Mock(
                repo="o/r",
                assessment=mock.Mock(category="healthy"),
                memo_path=os.path.join(d, "o__r-memo.md"),
                analysed=True,
            )
            config = Config(
                repos=["o/a", "o/b"],
                since="x",
                work_dir=os.path.join(d, "repos"),
                output_dir=d,
            )
            with mock.patch.object(agent, "run_repo", return_value=fake_result) as mock_run_repo:
                fleet = run_fleet(config)

            self.assertEqual(mock_run_repo.call_count, 2)
            self.assertTrue(os.path.exists(fleet.report_path))
            self.assertEqual(os.path.basename(fleet.report_path), "fleet-report.md")

    def test_one_failing_repo_does_not_abort_fleet(self):
        with tempfile.TemporaryDirectory() as d:
            good = mock.Mock(
                repo="o/good",
                assessment=mock.Mock(category="healthy"),
                memo_path=os.path.join(d, "o__good-memo.md"),
                analysed=True,
            )

            def side_effect(repo, **kwargs):
                if repo == "o/bad":
                    raise RuntimeError("GitHub API error for o/bad: Not Found")
                return good

            config = Config(
                repos=["o/bad", "o/good"],
                since="x",
                work_dir=os.path.join(d, "repos"),
                output_dir=d,
            )
            with mock.patch.object(agent, "run_repo", side_effect=side_effect):
                fleet = run_fleet(config)

            # The good repo still produced a result and the report was written.
            self.assertEqual(len(fleet.results), 1)
            self.assertTrue(os.path.exists(fleet.report_path))
            self.assertIn("Failed to analyse", fleet.report_markdown)
            self.assertIn("o/bad", fleet.report_markdown)


if __name__ == "__main__":
    unittest.main()
