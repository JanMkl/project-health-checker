import unittest

from github_summary_agent.backends import (
    BACKEND_COMMANDS,
    CODEX,
    CURSOR,
    DEFAULT_BACKEND,
    KIRO,
    SUPPORTED_BACKENDS,
    UnknownBackendError,
    get_backend,
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

    def test_backend_commands_match_names(self):
        self.assertEqual(BACKEND_COMMANDS, {KIRO, CODEX, CURSOR})

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


if __name__ == "__main__":
    unittest.main()
