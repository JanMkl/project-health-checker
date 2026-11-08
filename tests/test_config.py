import os
import tempfile
import unittest

from health_checker_agent.config import (
    ConfigError,
    dump_config,
    load_config,
    parse_config,
    save_config,
    with_repos,
)


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


class DumpAndSaveConfigTests(unittest.TestCase):
    def test_dump_round_trips(self):
        cfg = parse_config(
            'since = "90 days ago"\n'
            'until = "2026-11-01"\n'
            'backend = "codex"\n'
            'repos = ["o/a", "o/b"]\n'
        )
        reparsed = parse_config(dump_config(cfg))
        self.assertEqual(reparsed.repos, ["o/a", "o/b"])
        self.assertEqual(reparsed.since, "90 days ago")
        self.assertEqual(reparsed.until, "2026-11-01")
        self.assertEqual(reparsed.backend, "codex")

    def test_dump_omits_until_when_none(self):
        cfg = parse_config('since = "x"\nrepos = ["o/a"]\n')
        self.assertNotIn("until", dump_config(cfg))

    def test_save_config_writes_and_reloads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            cfg = parse_config('since = "x"\nrepos = ["o/a"]\n')
            save_config(path, with_repos(cfg, ["o/a", "o/b", "o/c"]))
            self.assertEqual(load_config(path).repos, ["o/a", "o/b", "o/c"])

    def test_with_repos_replaces_list(self):
        cfg = parse_config('since = "x"\nrepos = ["o/a"]\n')
        self.assertEqual(with_repos(cfg, ["o/b", "o/c"]).repos, ["o/b", "o/c"])
        # Original is unchanged (frozen dataclass copy).
        self.assertEqual(cfg.repos, ["o/a"])

    def test_save_escapes_special_characters(self):
        # A value containing a quote must round-trip safely.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            cfg = parse_config('since = "a \\" b"\nrepos = ["o/a"]\n')
            save_config(path, cfg)
            self.assertEqual(load_config(path).since, 'a " b')


if __name__ == "__main__":
    unittest.main()
