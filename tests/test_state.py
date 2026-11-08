import os
import tempfile
import unittest

from health_checker_agent.git_log_tool import Commit, GitLog
from health_checker_agent.issues_tool import Issue, IssueCollection
from health_checker_agent.pulls_tool import PullRequest, PullRequestCollection
from health_checker_agent.state import (
    compute_fingerprint,
    load_fingerprint,
    save_state,
    state_path,
)


def _log(n=1):
    commits = [Commit(f"h{i}", "a", "a@x", "2026-10-01T00:00:00", "m") for i in range(n)]
    return GitLog(since="x", until=None, commits=commits)


def _issues(state, n=0):
    items = [Issue(i, "t", "u", f"2026-10-0{i+1}T00:00:00Z", state) for i in range(n)]
    return IssueCollection(repo="o/r", state=state, issues=items)


def _pulls(state, n=0):
    items = [PullRequest(i, "t", "u", f"2026-09-0{i+1}T00:00:00Z", state) for i in range(n)]
    return PullRequestCollection(repo="o/r", state=state, pulls=items)


class FingerprintTests(unittest.TestCase):
    def test_same_inputs_same_digest(self):
        fp1 = compute_fingerprint(_log(2), _issues("open", 1), _issues("closed", 1), _pulls("open", 1), _pulls("closed", 1))
        fp2 = compute_fingerprint(_log(2), _issues("open", 1), _issues("closed", 1), _pulls("open", 1), _pulls("closed", 1))
        self.assertEqual(fp1.digest(), fp2.digest())

    def test_new_commit_changes_digest(self):
        fp1 = compute_fingerprint(_log(1), _issues("open"), _issues("closed"), _pulls("open"), _pulls("closed"))
        fp2 = compute_fingerprint(_log(2), _issues("open"), _issues("closed"), _pulls("open"), _pulls("closed"))
        self.assertNotEqual(fp1.digest(), fp2.digest())

    def test_new_issue_changes_digest(self):
        fp1 = compute_fingerprint(_log(1), _issues("open", 1), _issues("closed"), _pulls("open"), _pulls("closed"))
        fp2 = compute_fingerprint(_log(1), _issues("open", 2), _issues("closed"), _pulls("open"), _pulls("closed"))
        self.assertNotEqual(fp1.digest(), fp2.digest())


class StatePersistenceTests(unittest.TestCase):
    def test_round_trip(self):
        fp = compute_fingerprint(_log(1), _issues("open"), _issues("closed"), _pulls("open"), _pulls("closed"))
        with tempfile.TemporaryDirectory() as d:
            path = state_path(d, "o__r")
            save_state(path, fp, os.path.join(d, "o__r-memo.md"))
            loaded = load_fingerprint(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.digest(), fp.digest())

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_fingerprint("/nonexistent/state.json"))


if __name__ == "__main__":
    unittest.main()
