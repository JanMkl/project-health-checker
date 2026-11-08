import os
import tempfile
import unittest

from health_checker_agent.credentials import CREDENTIAL_ENV_VARS, CredentialStore


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = CredentialStore(self.dir)
        self._saved_env = {
            v: os.environ.get(v) for v in CREDENTIAL_ENV_VARS.values()
        }
        for v in CREDENTIAL_ENV_VARS.values():
            os.environ.pop(v, None)

    def tearDown(self):
        for var, value in self._saved_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_empty_when_no_file(self):
        self.assertEqual(self.store.load(), {})
        self.assertEqual(
            self.store.status(),
            {"github_token": False, "openai_api_key": False, "cursor_api_key": False},
        )

    def test_save_and_load(self):
        self.store.save({"github_token": "ghp_x", "openai_api_key": "sk-y"})
        loaded = self.store.load()
        self.assertEqual(loaded["github_token"], "ghp_x")
        self.assertEqual(loaded["openai_api_key"], "sk-y")

    def test_save_applies_to_environment(self):
        self.store.save({"github_token": "ghp_x"})
        self.assertEqual(os.environ["GITHUB_AUTH_TOKEN"], "ghp_x")

    def test_file_permissions_are_restrictive(self):
        self.store.save({"cursor_api_key": "key"})
        mode = os.stat(self.store.path).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_blank_value_removes_key(self):
        self.store.save({"github_token": "ghp_x"})
        self.store.save({"github_token": ""})
        self.assertNotIn("github_token", self.store.load())

    def test_update_merges_without_dropping_others(self):
        self.store.save({"github_token": "ghp_x"})
        self.store.save({"openai_api_key": "sk-y"})
        loaded = self.store.load()
        self.assertEqual(loaded.get("github_token"), "ghp_x")
        self.assertEqual(loaded.get("openai_api_key"), "sk-y")

    def test_unknown_keys_ignored(self):
        self.store.save({"not_a_cred": "value", "github_token": "ghp_x"})
        self.assertEqual(set(self.store.load()), {"github_token"})

    def test_status_reflects_environment_fallback(self):
        # A credential present only in the environment still counts as "set".
        os.environ["CURSOR_API_KEY"] = "env-key"
        self.assertTrue(self.store.status()["cursor_api_key"])


if __name__ == "__main__":
    unittest.main()
