import unittest
from unittest import mock

from health_checker_agent.adopters_tool import (
    Adopters,
    _candidate_urls,
    read_adopters,
)

FETCH_TEXT = "health_checker_agent.adopters_tool.fetch_text"


class CandidateUrlTests(unittest.TestCase):
    def test_community_repo_is_tried_first(self):
        candidates = _candidate_urls("metal3-io/metal3-dev-env", "https://api.github.com")
        first_source, first_url = candidates[0]
        self.assertEqual(first_source, "metal3-io/community:ADOPTERS.md")
        self.assertIn("/repos/metal3-io/community/contents/ADOPTERS.md", first_url)

    def test_project_repo_is_also_probed(self):
        sources = [s for s, _ in _candidate_urls("o/proj", "https://api.github.com")]
        self.assertIn("o/proj:ADOPTERS.md", sources)
        self.assertIn("o/.github:ADOPTERS.md", sources)


class ReadAdoptersTests(unittest.TestCase):
    def test_found_in_community_repo(self):
        # fetch_text returns content for the first (community) candidate.
        def fake_fetch(url, *, token=None, timeout=60):
            if "metal3-io/community" in url:
                return "# Adopters\n\n| Ericsson | ... |\n"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            a = read_adopters("metal3-io/metal3-dev-env")
        self.assertTrue(a.found)
        self.assertEqual(a.source, "metal3-io/community:ADOPTERS.md")
        self.assertIn("Ericsson", a.content)

    def test_falls_back_to_project_repo(self):
        def fake_fetch(url, *, token=None, timeout=60):
            # Only the project repo has the file.
            if "/repos/o/proj/contents/ADOPTERS.md" in url:
                return "project adopters"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            a = read_adopters("o/proj")
        self.assertTrue(a.found)
        self.assertEqual(a.source, "o/proj:ADOPTERS.md")

    def test_not_found_returns_empty(self):
        with mock.patch(FETCH_TEXT, return_value=None):
            a = read_adopters("o/proj")
        self.assertFalse(a.found)
        self.assertIsNone(a.source)
        self.assertIsNone(a.content)

    def test_blank_content_is_treated_as_not_found(self):
        with mock.patch(FETCH_TEXT, return_value="   \n  "):
            a = read_adopters("o/proj")
        self.assertFalse(a.found)

    def test_stops_at_first_hit(self):
        calls = []

        def fake_fetch(url, *, token=None, timeout=60):
            calls.append(url)
            return "found" if "community" in url else None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            read_adopters("o/proj")
        # The community repo is the first candidate, so only one call is made.
        self.assertEqual(len(calls), 1)


class AdoptersToTextTests(unittest.TestCase):
    def test_to_text_when_found(self):
        a = Adopters(repo="o/r", source="o/community:ADOPTERS.md", content="# Adopters\nEricsson")
        text = a.to_text()
        self.assertIn("Adopters for o/r", text)
        self.assertIn("source: o/community:ADOPTERS.md", text)
        self.assertIn("Ericsson", text)

    def test_to_text_when_absent(self):
        a = Adopters(repo="o/r", source=None, content=None)
        self.assertIn("no ADOPTERS file found", a.to_text())
        self.assertFalse(a.found)


class FoundPresenceTests(unittest.TestCase):
    def test_found_true_for_any_nonempty_content(self):
        # A table, a bare link-out stub, and a plain list all count as "found".
        table = "| Name |\n|---|\n| Ericsson |\n"
        linkout = "# Adopters\n\nSee https://example.com/adopters for the list.\n"
        bullets = "# Adopters\n\n- Ericsson\n- Red Hat\n"
        for content in (table, linkout, bullets):
            self.assertTrue(
                Adopters(repo="o/r", source="o/community:ADOPTERS.md", content=content).found
            )

    def test_found_false_for_empty_or_missing(self):
        self.assertFalse(Adopters(repo="o/r", source=None, content=None).found)
        self.assertFalse(Adopters(repo="o/r", source="s", content="").found)
        self.assertFalse(Adopters(repo="o/r", source="s", content="   \n ").found)


if __name__ == "__main__":
    unittest.main()
