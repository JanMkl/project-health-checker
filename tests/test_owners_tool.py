import unittest
from unittest import mock

from health_checker_agent.owners_tool import (
    Owners,
    _candidate_urls,
    read_owners,
)

FETCH_TEXT = "health_checker_agent.owners_tool.fetch_text"


class CandidateUrlTests(unittest.TestCase):
    def test_project_root_owners_tried_first(self):
        candidates = _candidate_urls("o/proj", "https://api.github.com")
        first_source, first_url = candidates[0]
        self.assertEqual(first_source, "o/proj:OWNERS")
        # No .md extension, and in the project repo.
        self.assertIn("/repos/o/proj/contents/OWNERS", first_url)
        self.assertNotIn("OWNERS.md", first_url)

    def test_probes_github_subdir(self):
        sources = [s for s, _ in _candidate_urls("o/proj", "https://api.github.com")]
        self.assertIn("o/proj:.github/OWNERS", sources)

    def test_does_not_probe_org_level_repos(self):
        # OWNERS is project-specific; community/.github org repos are not probed.
        sources = [s for s, _ in _candidate_urls("o/proj", "https://api.github.com")]
        self.assertFalse(any("o/community" in s for s in sources))
        self.assertFalse(any(s.startswith("o/.github:") for s in sources))


class ReadOwnersTests(unittest.TestCase):
    def test_found_in_root(self):
        def fake_fetch(url, *, token=None, timeout=60):
            if url.endswith("/contents/OWNERS"):
                return "approvers:\n- alice\nreviewers:\n- bob\n"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            o = read_owners("o/proj")
        self.assertTrue(o.found)
        self.assertEqual(o.source, "o/proj:OWNERS")
        self.assertIn("alice", o.content)

    def test_falls_back_to_github_subdir(self):
        def fake_fetch(url, *, token=None, timeout=60):
            if url.endswith("/contents/.github/OWNERS"):
                return "approvers:\n- carol\n"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            o = read_owners("o/proj")
        self.assertTrue(o.found)
        self.assertEqual(o.source, "o/proj:.github/OWNERS")

    def test_not_found_returns_empty(self):
        with mock.patch(FETCH_TEXT, return_value=None):
            o = read_owners("o/proj")
        self.assertFalse(o.found)
        self.assertIsNone(o.source)
        self.assertIsNone(o.content)

    def test_stops_at_first_hit(self):
        calls = []

        def fake_fetch(url, *, token=None, timeout=60):
            calls.append(url)
            return "approvers:\n- a\n" if url.endswith("/contents/OWNERS") else None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            read_owners("o/proj")
        self.assertEqual(len(calls), 1)


class OwnersToTextTests(unittest.TestCase):
    def test_to_text_when_found(self):
        o = Owners(repo="o/r", source="o/r:OWNERS", content="approvers:\n- alice")
        text = o.to_text()
        self.assertIn("Owners for o/r", text)
        self.assertIn("source: o/r:OWNERS", text)
        self.assertIn("alice", text)

    def test_to_text_when_absent(self):
        o = Owners(repo="o/r", source=None, content=None)
        self.assertIn("no OWNERS file found", o.to_text())
        self.assertFalse(o.found)

    def test_found_requires_nonempty_content(self):
        self.assertFalse(Owners(repo="o/r", source="s", content="").found)
        self.assertFalse(Owners(repo="o/r", source="s", content="  \n").found)
        self.assertTrue(Owners(repo="o/r", source="s", content="x").found)


if __name__ == "__main__":
    unittest.main()
