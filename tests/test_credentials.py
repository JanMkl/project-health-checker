import os
import unittest

from health_checker_agent.credentials import CREDENTIAL_ENV_VARS, CredentialStore


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = CredentialStore()
        # Snapshot and clear the credential env vars for isolation.
        self._saved_env = {v: os.environ.get(v) for v in CREDENTIAL_ENV_VARS.values()}
        for v in CREDENTIAL_ENV_VARS.values():
            os.environ.pop(v, None)

    def tearDown(self):
        for var, value in self._saved_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_empty_status_when_unset(self):
        self.assertEqual(
            self.store.status(),
            {"github_token": False, "openai_api_key": False, "cursor_api_key": False},
        )

    def test_save_sets_environment(self):
        self.store.save({"github_token": "ghp_x", "openai_api_key": "sk-y"})
        self.assertEqual(os.environ["GITHUB_AUTH_TOKEN"], "ghp_x")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-y")
        self.assertTrue(self.store.status()["github_token"])
        self.assertTrue(self.store.status()["openai_api_key"])

    def test_blank_value_keeps_existing(self):
        self.store.save({"github_token": "ghp_x"})
        # A blank value must not wipe a previously-set credential.
        self.store.save({"github_token": ""})
        self.assertEqual(os.environ.get("GITHUB_AUTH_TOKEN"), "ghp_x")

    def test_clear_removes_env(self):
        self.store.save({"cursor_api_key": "key"})
        self.store.clear(["cursor_api_key"])
        self.assertIsNone(os.environ.get("CURSOR_API_KEY"))
        self.assertFalse(self.store.status()["cursor_api_key"])

    def test_update_merges_without_dropping_others(self):
        self.store.save({"github_token": "ghp_x"})
        self.store.save({"openai_api_key": "sk-y"})
        self.assertEqual(os.environ.get("GITHUB_AUTH_TOKEN"), "ghp_x")
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-y")

    def test_unknown_keys_ignored(self):
        self.store.save({"not_a_cred": "value", "github_token": "ghp_x"})
        self.assertEqual(os.environ.get("GITHUB_AUTH_TOKEN"), "ghp_x")
        self.assertNotIn("not_a_cred", os.environ)

    def test_status_reflects_preexisting_environment(self):
        # A credential exported in the shell before launch counts as "set".
        os.environ["CURSOR_API_KEY"] = "env-key"
        self.assertTrue(self.store.status()["cursor_api_key"])

    def test_apply_is_noop(self):
        # apply() exists for API compatibility and must not raise.
        self.store.apply()


if __name__ == "__main__":
    unittest.main()
