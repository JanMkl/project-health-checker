import unittest
from unittest import mock

from health_checker_agent.security_tool import (
    SecurityPolicy,
    _candidate_urls,
    read_security_policy,
)

FETCH_TEXT = "health_checker_agent.security_tool.fetch_text"


class CandidateUrlTests(unittest.TestCase):
    def test_project_repo_is_tried_first(self):
        candidates = _candidate_urls("o/proj", "https://api.github.com")
        first_source, first_url = candidates[0]
        self.assertEqual(first_source, "o/proj:SECURITY.md")
        self.assertIn("/repos/o/proj/contents/SECURITY.md", first_url)

    def test_covers_known_locations(self):
        sources = [s for s, _ in _candidate_urls("o/proj", "https://api.github.com")]
        # .github/ and docs/ variants, the Kubernetes SECURITY_CONTACTS, and the
        # org-level .github and community fallbacks are all probed.
        self.assertIn("o/proj:.github/SECURITY.md", sources)
        self.assertIn("o/proj:docs/SECURITY.md", sources)
        self.assertIn("o/proj:SECURITY_CONTACTS", sources)
        self.assertIn("o/.github:SECURITY.md", sources)
        self.assertIn("o/community:SECURITY.md", sources)


class ReadSecurityPolicyTests(unittest.TestCase):
    def test_found_in_project_root(self):
        def fake_fetch(url, *, token=None, timeout=60):
            if "/repos/o/proj/contents/SECURITY.md" in url:
                return "# Security Policy\n\nReport to security@example.com"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            s = read_security_policy("o/proj")
        self.assertTrue(s.found)
        self.assertEqual(s.source, "o/proj:SECURITY.md")
        self.assertIn("security@example.com", s.content)

    def test_falls_back_to_security_contacts(self):
        def fake_fetch(url, *, token=None, timeout=60):
            if url.endswith("/contents/SECURITY_CONTACTS"):
                return "# security contacts\n- alice"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            s = read_security_policy("o/proj")
        self.assertTrue(s.found)
        self.assertEqual(s.source, "o/proj:SECURITY_CONTACTS")

    def test_falls_back_to_org_github_repo(self):
        def fake_fetch(url, *, token=None, timeout=60):
            if "/repos/o/.github/contents/SECURITY.md" in url:
                return "org default security policy"
            return None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            s = read_security_policy("o/proj")
        self.assertTrue(s.found)
        self.assertEqual(s.source, "o/.github:SECURITY.md")

    def test_not_found_returns_empty(self):
        with mock.patch(FETCH_TEXT, return_value=None):
            s = read_security_policy("o/proj")
        self.assertFalse(s.found)
        self.assertIsNone(s.source)
        self.assertIsNone(s.content)

    def test_stops_at_first_hit(self):
        calls = []

        def fake_fetch(url, *, token=None, timeout=60):
            calls.append(url)
            return "found" if url.endswith("/contents/SECURITY.md") else None

        with mock.patch(FETCH_TEXT, side_effect=fake_fetch):
            read_security_policy("o/proj")
        # SECURITY.md in the repo root is the first candidate.
        self.assertEqual(len(calls), 1)


class SecurityToTextTests(unittest.TestCase):
    def test_to_text_when_found(self):
        s = SecurityPolicy(repo="o/r", source="o/r:SECURITY.md", content="# Security\nReport privately")
        text = s.to_text()
        self.assertIn("Security policy for o/r", text)
        self.assertIn("source: o/r:SECURITY.md", text)
        self.assertIn("Report privately", text)

    def test_to_text_when_absent(self):
        s = SecurityPolicy(repo="o/r", source=None, content=None)
        self.assertIn("no SECURITY.md or SECURITY_CONTACTS file found", s.to_text())
        self.assertFalse(s.found)

    def test_found_requires_nonempty_content(self):
        self.assertFalse(SecurityPolicy(repo="o/r", source="s", content="").found)
        self.assertFalse(SecurityPolicy(repo="o/r", source="s", content="  \n ").found)
        self.assertTrue(SecurityPolicy(repo="o/r", source="s", content="x").found)


if __name__ == "__main__":
    unittest.main()
