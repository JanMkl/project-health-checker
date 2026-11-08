import unittest

from health_checker_agent.git_log_tool import Commit, GitLog
from health_checker_agent.health import (
    ATTENTION,
    HEALTHY,
    INVESTIGATE,
    classify_health,
)
from health_checker_agent.issues_tool import Issue, IssueCollection
from health_checker_agent.pulls_tool import PullRequest, PullRequestCollection


def _log(n):
    return GitLog(
        since="x",
        until=None,
        commits=[Commit(f"h{i}", "a", "a@x", "d", "m") for i in range(n)],
    )


def _issues(state, n):
    return IssueCollection(
        repo="o/r",
        state=state,
        issues=[Issue(i, "t", "u", "d", state) for i in range(n)],
    )


def _pulls(state, n):
    return PullRequestCollection(
        repo="o/r",
        state=state,
        pulls=[PullRequest(i, "t", "u", "d", state) for i in range(n)],
    )


class ClassifyHealthTests(unittest.TestCase):
    def test_dormant_is_investigate(self):
        a = classify_health("o/r", _log(0), _issues("open", 0), _issues("closed", 0), _pulls("open", 0), _pulls("closed", 0))
        self.assertEqual(a.category, INVESTIGATE)

    def test_open_work_no_throughput_is_attention(self):
        a = classify_health("o/r", _log(0), _issues("open", 3), _issues("closed", 0), _pulls("open", 0), _pulls("closed", 0))
        self.assertEqual(a.category, ATTENTION)

    def test_large_backlog_nothing_closed_is_attention(self):
        a = classify_health("o/r", _log(2), _issues("open", 6), _issues("closed", 0), _pulls("open", 0), _pulls("closed", 0))
        self.assertEqual(a.category, ATTENTION)

    def test_growing_backlog_is_attention(self):
        # open (20) > 3x closed (3) and >= 10
        a = classify_health("o/r", _log(5), _issues("open", 15), _issues("closed", 2), _pulls("open", 5), _pulls("closed", 1))
        self.assertEqual(a.category, ATTENTION)

    def test_active_keeping_up_is_healthy(self):
        a = classify_health("o/r", _log(10), _issues("open", 2), _issues("closed", 5), _pulls("open", 1), _pulls("closed", 8))
        self.assertEqual(a.category, HEALTHY)

    def test_reason_is_populated(self):
        a = classify_health("o/r", _log(10), _issues("open", 2), _issues("closed", 5), _pulls("open", 1), _pulls("closed", 8))
        self.assertTrue(a.reason)
        self.assertEqual(a.repo, "o/r")


if __name__ == "__main__":
    unittest.main()
