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


class BackendsTests(unittest.TestCase):
    def test_default_backend_is_kiro(self):
        self.assertEqual(DEFAULT_BACKEND, KIRO)

    def test_supported_backends(self):
        self.assertEqual(set(SUPPORTED_BACKENDS), {KIRO, CODEX, CURSOR})

    def test_backend_commands_match_names(self):
        self.assertEqual(BACKEND_COMMANDS, {KIRO, CODEX, CURSOR})

    def test_kiro_args(self):
        args = get_backend(KIRO).build_args()
        self.assertEqual(args[0], "kiro-cli")
        self.assertIn("chat", args)
        self.assertIn("--no-interactive", args)

    def test_codex_args(self):
        args = get_backend(CODEX).build_args()
        self.assertEqual(args[0], "codex")
        self.assertIn("exec", args)

    def test_cursor_args(self):
        args = get_backend(CURSOR).build_args()
        self.assertEqual(args[0], "cursor-agent")
        self.assertIn("--print", args)

    def test_unknown_backend_raises(self):
        with self.assertRaises(UnknownBackendError):
            get_backend("gemini")


if __name__ == "__main__":
    unittest.main()
