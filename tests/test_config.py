import os
import tempfile
import unittest

from github_summary_agent.config import ConfigError, load_config, parse_config


class ParseConfigTests(unittest.TestCase):
    def test_minimal_valid_config(self):
        cfg = parse_config('since = "90 days ago"\nrepos = ["o/a", "o/b"]\n')
        self.assertEqual(cfg.repos, ["o/a", "o/b"])
        self.assertEqual(cfg.since, "90 days ago")
        self.assertIsNone(cfg.until)
        self.assertEqual(cfg.work_dir, "output/repos")
        self.assertEqual(cfg.output_dir, "output")
        # Backend defaults to kiro-cli when unspecified.
        self.assertEqual(cfg.backend, "kiro-cli")

    def test_backend_from_config(self):
        cfg = parse_config('since = "x"\nbackend = "codex"\nrepos = ["o/a"]\n')
        self.assertEqual(cfg.backend, "codex")

    def test_unknown_backend_raises(self):
        with self.assertRaises(ConfigError):
            parse_config('since = "x"\nbackend = "gemini"\nrepos = ["o/a"]\n')

    def test_all_fields(self):
        cfg = parse_config(
            'since = "2022-01-01"\n'
            'until = "2026-01-01"\n'
            'work_dir = "wd"\n'
            'output_dir = "od"\n'
            'repos = ["o/a"]\n'
        )
        self.assertEqual(cfg.until, "2026-01-01")
        self.assertEqual(cfg.work_dir, "wd")
        self.assertEqual(cfg.output_dir, "od")

    def test_missing_repos_raises(self):
        with self.assertRaises(ConfigError):
            parse_config('since = "x"\n')

    def test_empty_repos_raises(self):
        with self.assertRaises(ConfigError):
            parse_config('since = "x"\nrepos = []\n')

    def test_missing_since_raises(self):
        with self.assertRaises(ConfigError):
            parse_config('repos = ["o/a"]\n')

    def test_bad_repo_shape_raises(self):
        with self.assertRaises(ConfigError):
            parse_config('since = "x"\nrepos = ["not-a-repo"]\n')

    def test_malformed_toml_raises(self):
        with self.assertRaises(ConfigError):
            parse_config("this is = = not toml")


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(ConfigError):
            load_config("/nonexistent/repos.toml")

    def test_loads_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nrepos = ["o/a"]\n')
            cfg = load_config(path)
            self.assertEqual(cfg.repos, ["o/a"])


if __name__ == "__main__":
    unittest.main()
