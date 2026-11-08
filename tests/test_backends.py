import unittest
from unittest import mock

from health_checker_agent.backends import (
    BACKEND_COMMANDS,
    CODEX,
    CURSOR,
    DEFAULT_BACKEND,
    KIRO,
    KIRO_LOGGED_IN,
    KIRO_LOGGED_OUT,
    KIRO_NOT_INSTALLED,
    KIRO_UNKNOWN,
    SUPPORTED_BACKENDS,
    UnknownBackendError,
    get_backend,
    kiro_login_status,
)


class _FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class BackendsTests(unittest.TestCase):
    def test_default_backend_is_kiro(self):
        self.assertEqual(DEFAULT_BACKEND, KIRO)

    def test_supported_backends(self):
        self.assertEqual(set(SUPPORTED_BACKENDS), {KIRO, CODEX, CURSOR})

    def test_backend_commands_include_all_candidate_executables(self):
        # Cursor ships under both "cursor-agent" and the bare "agent".
        self.assertEqual(BACKEND_COMMANDS, {KIRO, CODEX, CURSOR, "agent"})

    def test_cursor_backend_lists_both_executables(self):
        self.assertEqual(get_backend(CURSOR).executables, ("cursor-agent", "agent"))

    def test_kiro_argv(self):
        argv = get_backend(KIRO).argv
        self.assertEqual(argv[0], "kiro-cli")
        self.assertIn("chat", argv)
        self.assertIn("--no-interactive", argv)

    def test_codex_argv(self):
        argv = get_backend(CODEX).argv
        self.assertEqual(argv[0], "codex")
        self.assertIn("exec", argv)
        self.assertIn("-", argv)

    def test_cursor_argv(self):
        argv = get_backend(CURSOR).argv
        self.assertEqual(argv[0], "cursor-agent")
        self.assertIn("--print", argv)
        self.assertIn("--output-format", argv)
        # --trust clears the non-interactive workspace-trust prompt.
        self.assertIn("--trust", argv)

    def test_unknown_backend_raises(self):
        with self.assertRaises(UnknownBackendError):
            get_backend("gemini")


class StdoutBackendRunTests(unittest.TestCase):
    def test_kiro_reads_stdout(self):
        calls = []

        def runner(argv, *, timeout=None, stdin_input=None):
            calls.append((argv, stdin_input))
            return _FakeResult(stdout="  # Memo\n\nbody  \n")

        out = get_backend(KIRO).generate("PROMPT", runner, 120)
        self.assertEqual(out, "# Memo\n\nbody")
        # Prompt fed on stdin; argv is the kiro invocation.
        self.assertEqual(calls[0][1], "PROMPT")
        self.assertEqual(calls[0][0][0], "kiro-cli")

    def test_cursor_reads_stdout(self):
        def runner(argv, *, timeout=None, stdin_input=None):
            return _FakeResult(stdout="cursor memo")

        out = get_backend(CURSOR).generate("PROMPT", runner, None)
        self.assertEqual(out, "cursor memo")


class CursorExecutableResolutionTests(unittest.TestCase):
    def _run_with_which(self, available):
        from unittest import mock

        captured = {}

        def runner(argv, *, timeout=None, stdin_input=None):
            captured["argv"] = argv
            return _FakeResult(stdout="ok")

        with mock.patch(
            "health_checker_agent.backends.shutil.which",
            side_effect=lambda e: e if e in available else None,
        ):
            get_backend(CURSOR).generate("PROMPT", runner, None)
        return captured["argv"]

    def test_prefers_cursor_agent_when_present(self):
        argv = self._run_with_which({"cursor-agent", "agent"})
        self.assertEqual(argv[0], "cursor-agent")

    def test_falls_back_to_bare_agent(self):
        # Only the bare `agent` entry point is installed.
        argv = self._run_with_which({"agent"})
        self.assertEqual(argv[0], "agent")
        # The rest of the invocation is unchanged.
        self.assertEqual(argv[1:], ["--print", "--output-format", "text", "--trust"])

    def test_falls_back_to_primary_name_when_none_found(self):
        # Neither is installed: use the primary name so the error names it.
        argv = self._run_with_which(set())
        self.assertEqual(argv[0], "cursor-agent")


class CodexBackendRunTests(unittest.TestCase):
    def test_codex_reads_last_message_file_not_stdout(self):
        captured = {}

        def runner(argv, *, timeout=None, stdin_input=None):
            # codex writes the clean memo to the --output-last-message file;
            # stdout is a noisy event log that must be ignored.
            self.assertIn("--output-last-message", argv)
            path = argv[argv.index("--output-last-message") + 1]
            captured["path"] = path
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# Codex Memo\n\nclean body\n")
            return _FakeResult(stdout="OpenAI Codex v0.0\n--- framing ---\nignored")

        out = get_backend(CODEX).generate("PROMPT", runner, 300)
        self.assertEqual(out, "# Codex Memo\n\nclean body")

    def test_codex_cleans_up_temp_file(self):
        import os

        seen_path = {}

        def runner(argv, *, timeout=None, stdin_input=None):
            path = argv[argv.index("--output-last-message") + 1]
            seen_path["path"] = path
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("memo")
            return _FakeResult(stdout="noise")

        get_backend(CODEX).generate("PROMPT", runner, 300)
        # The temp file is removed after the memo is read.
        self.assertFalse(os.path.exists(seen_path["path"]))


class KiroLoginStatusTests(unittest.TestCase):
    def test_logged_in_when_whoami_exits_zero(self):
        with mock.patch(
            "health_checker_agent.commands.run_command",
            return_value=_FakeResult(stdout="Logged in", returncode=0),
        ):
            self.assertEqual(kiro_login_status(), KIRO_LOGGED_IN)

    def test_logged_out_when_whoami_exits_nonzero(self):
        with mock.patch(
            "health_checker_agent.commands.run_command",
            return_value=_FakeResult(stdout="Not logged in", returncode=1),
        ):
            self.assertEqual(kiro_login_status(), KIRO_LOGGED_OUT)

    def test_not_installed_when_binary_missing(self):
        with mock.patch(
            "health_checker_agent.commands.run_command",
            side_effect=FileNotFoundError(),
        ):
            self.assertEqual(kiro_login_status(), KIRO_NOT_INSTALLED)

    def test_unknown_on_other_errors(self):
        with mock.patch(
            "health_checker_agent.commands.run_command",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(kiro_login_status(), KIRO_UNKNOWN)

    def test_probes_kiro_cli_whoami(self):
        with mock.patch(
            "health_checker_agent.commands.run_command",
            return_value=_FakeResult(returncode=0),
        ) as m:
            kiro_login_status()
        args = m.call_args.args[0]
        self.assertEqual(args, ["kiro-cli", "whoami"])
        # Probed non-fatally (check=False) so a logged-out exit code is not an
        # exception.
        self.assertFalse(m.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
