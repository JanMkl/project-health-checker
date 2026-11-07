import os
import tempfile
import unittest
from unittest import mock

from github_summary_agent import __main__ as cli
from github_summary_agent.__main__ import build_parser, main


class ParserTests(unittest.TestCase):
    def test_requires_config_or_repo(self):
        # argparse itself allows empty; main() enforces the xor via parser.error.
        with self.assertRaises(SystemExit):
            main([])

    def test_repo_requires_since(self):
        with self.assertRaises(SystemExit):
            main(["--repo", "o/r"])

    def test_config_and_repo_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            main(["--config", "x.toml", "--repo", "o/r"])

    def test_parses_work_dir_and_force(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.toml", "--work-dir", "wd", "--force"])
        self.assertEqual(args.work_dir, "wd")
        self.assertTrue(args.force)

    def test_parses_pptx_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.toml", "--pptx"])
        self.assertTrue(args.pptx)
        default = parser.parse_args(["--config", "c.toml"])
        self.assertFalse(default.pptx)

    def test_parses_backend_choice(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.toml", "--backend", "codex"])
        self.assertEqual(args.backend, "codex")
        # Default is None so config can supply its own value.
        self.assertIsNone(parser.parse_args(["--config", "c.toml"]).backend)

    def test_rejects_unknown_backend(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--config", "c.toml", "--backend", "gemini"])


class MainSingleRepoTests(unittest.TestCase):
    @mock.patch.object(cli, "run_repo")
    def test_single_repo_invokes_run_repo(self, mock_run_repo):
        mock_run_repo.return_value = mock.Mock(
            repo="o/r",
            assessment=mock.Mock(category="healthy"),
            memo_path="output/o__r-memo.md",
            analysed=True,
        )
        code = main(["--repo", "o/r", "--since", "30 days ago"])
        self.assertEqual(code, 0)
        mock_run_repo.assert_called_once()
        self.assertEqual(mock_run_repo.call_args.args[0], "o/r")
        self.assertEqual(mock_run_repo.call_args.kwargs["since"], "30 days ago")
        # Defaults to kiro-cli when --backend is not given.
        self.assertEqual(mock_run_repo.call_args.kwargs["backend"], "kiro-cli")

    @mock.patch.object(cli, "run_repo")
    def test_single_repo_backend_override(self, mock_run_repo):
        mock_run_repo.return_value = mock.Mock(
            repo="o/r",
            assessment=mock.Mock(category="healthy"),
            memo_path="output/o__r-memo.md",
            analysed=True,
        )
        code = main(["--repo", "o/r", "--since", "x", "--backend", "cursor-agent"])
        self.assertEqual(code, 0)
        self.assertEqual(mock_run_repo.call_args.kwargs["backend"], "cursor-agent")

    @mock.patch.object(cli, "run_fleet")
    @mock.patch.object(cli, "run_repo")
    def test_single_repo_with_pptx_routes_through_run_fleet(
        self, mock_run_repo, mock_run_fleet
    ):
        # With --pptx, even a single repo should go through run_fleet so the
        # deck is produced, and the run_repo shortcut must be skipped.
        mock_run_fleet.return_value = mock.Mock(
            results=[mock.Mock(analysed=True)],
            report_path="output/fleet-report.md",
            pptx_path="output/fleet-summary.pptx",
        )
        code = main(["--repo", "o/r", "--since", "30 days ago", "--pptx"])
        self.assertEqual(code, 0)
        mock_run_repo.assert_not_called()
        mock_run_fleet.assert_called_once()
        self.assertTrue(mock_run_fleet.call_args.kwargs["pptx"])


class MainFleetTests(unittest.TestCase):
    @mock.patch.object(cli, "run_fleet")
    def test_config_invokes_run_fleet(self, mock_run_fleet):
        mock_run_fleet.return_value = mock.Mock(
            results=[mock.Mock(analysed=True), mock.Mock(analysed=False)],
            report_path="output/fleet-report.md",
            pptx_path=None,
        )
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nrepos = ["o/a", "o/b"]\n')
            code = main(["--config", path])

        self.assertEqual(code, 0)
        mock_run_fleet.assert_called_once()
        self.assertFalse(mock_run_fleet.call_args.kwargs["pptx"])

    @mock.patch.object(cli, "run_fleet")
    def test_config_with_pptx_passes_flag(self, mock_run_fleet):
        mock_run_fleet.return_value = mock.Mock(
            results=[mock.Mock(analysed=True)],
            report_path="output/fleet-report.md",
            pptx_path="output/fleet-summary.pptx",
        )
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nrepos = ["o/a"]\n')
            code = main(["--config", path, "--pptx"])

        self.assertEqual(code, 0)
        self.assertTrue(mock_run_fleet.call_args.kwargs["pptx"])

    @mock.patch.object(cli, "run_fleet")
    def test_backend_flag_overrides_config(self, mock_run_fleet):
        mock_run_fleet.return_value = mock.Mock(
            results=[mock.Mock(analysed=True)],
            report_path="output/fleet-report.md",
            pptx_path=None,
        )
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nbackend = "codex"\nrepos = ["o/a"]\n')
            # CLI --backend should win over the config's "codex".
            code = main(["--config", path, "--backend", "cursor-agent"])
        self.assertEqual(code, 0)
        config_arg = mock_run_fleet.call_args.args[0]
        self.assertEqual(config_arg.backend, "cursor-agent")

    @mock.patch.object(cli, "run_fleet")
    def test_backend_from_config_used_when_flag_absent(self, mock_run_fleet):
        mock_run_fleet.return_value = mock.Mock(
            results=[mock.Mock(analysed=True)],
            report_path="output/fleet-report.md",
            pptx_path=None,
        )
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nbackend = "codex"\nrepos = ["o/a"]\n')
            code = main(["--config", path])
        self.assertEqual(code, 0)
        self.assertEqual(mock_run_fleet.call_args.args[0].backend, "codex")

    @mock.patch.object(cli, "run_fleet", side_effect=RuntimeError("pptx missing"))
    def test_run_fleet_error_returns_exit_code_1(self, _mock_run_fleet):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\nrepos = ["o/a"]\n')
            code = main(["--config", path, "--pptx"])
        self.assertEqual(code, 1)

    def test_bad_config_returns_exit_code_2(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "repos.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('since = "x"\n')  # missing repos
            code = main(["--config", path])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
