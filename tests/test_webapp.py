import os
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient

from health_checker_agent.config import load_config
from health_checker_agent.webapp import create_app


def _write_config(path, repos=("metal3-io/metal3-dev-env",), since="90 days ago"):
    lines = [f'since = "{since}"', "repos = ["]
    lines += [f'    "{r}",' for r in repos]
    lines += ["]"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


class WebAppTestBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.dir, "repos.toml")
        self.secrets_dir = os.path.join(self.dir, "secrets")
        self.output_dir = os.path.join(self.dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        _write_config(self.config_path)
        # Point the config's output_dir at our temp output so memo/pptx routes
        # resolve there.
        with open(self.config_path, "a", encoding="utf-8") as fh:
            fh.write(f'output_dir = "{self.output_dir}"\n')

        # Record calls to the injected runner instead of running a real fleet.
        self.run_calls = []

        def fake_run_fleet(config, *, force=False, pptx=False):
            self.run_calls.append({"config": config, "force": force, "pptx": pptx})

        self.fake_run_fleet = fake_run_fleet
        # Inject a stub kiro-cli status so tests never shell out. Individual
        # tests can rebuild the app with a different status.
        self.kiro_status = "logged_out"
        self.app = create_app(
            config_path=self.config_path,
            credentials_dir=self.secrets_dir,
            run_fleet_fn=fake_run_fleet,
            kiro_status_fn=lambda: self.kiro_status,
        )
        # Do not auto-follow 303 redirects so we can assert them.
        self.client = TestClient(self.app, follow_redirects=False)

    def _config(self):
        return load_config(self.config_path)


class PageStructureTests(WebAppTestBase):
    PAGES = ("/", "/repositories", "/settings", "/credentials", "/run")

    def test_all_pages_render_with_nav_bar(self):
        for path in self.PAGES:
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            # Every page carries the shared navigation bar with all five links.
            self.assertIn("<nav>", r.text, path)
            for link, label in (
                ("/repositories", "Repositories"),
                ("/settings", "Settings"),
                ("/credentials", "Credentials"),
                ("/run", "Run analysis"),
                ("/", "Memos &amp; Presentation"),
            ):
                self.assertIn(f'href="{link}"', r.text, path)
                self.assertIn(label, r.text, path)

    def test_root_is_memos_page(self):
        r = self.client.get("/")
        self.assertIn("Memos", r.text)
        self.assertIn("Presentation", r.text)

    def test_active_link_is_marked(self):
        r = self.client.get("/settings")
        # The Settings link is marked active on the Settings page.
        self.assertIn('href="/settings" class="active"', r.text)

    def test_status_endpoint(self):
        r = self.client.get("/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["running"])
        self.assertIn("message", body)


class StatusVisibilityTests(WebAppTestBase):
    def test_status_only_on_run_page(self):
        self.assertIn("Analysis status", self.client.get("/run").text)
        for path in ("/", "/repositories", "/settings", "/credentials"):
            self.assertNotIn("Analysis status", self.client.get(path).text, path)


class RepoEditTests(WebAppTestBase):
    def test_repositories_page_lists_repos(self):
        page = self.client.get("/repositories").text
        self.assertIn("metal3-io/metal3-dev-env", page)

    def test_add_repo(self):
        r = self.client.post("/repos/add", data={"repo": "octocat/Hello-World"})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/repositories")
        self.assertIn("octocat/Hello-World", self._config().repos)

    def test_add_duplicate_repo_is_noop(self):
        self.client.post("/repos/add", data={"repo": "octocat/Hello-World"})
        self.client.post("/repos/add", data={"repo": "octocat/Hello-World"})
        repos = self._config().repos
        self.assertEqual(repos.count("octocat/Hello-World"), 1)

    def test_remove_repo(self):
        self.client.post("/repos/add", data={"repo": "octocat/Hello-World"})
        r = self.client.post("/repos/remove", data={"repo": "octocat/Hello-World"})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/repositories")
        self.assertNotIn("octocat/Hello-World", self._config().repos)

    def test_remove_last_repo_is_rejected(self):
        # The config requires a non-empty repo list; removing the only repo must
        # not wipe the file.
        only = self._config().repos
        self.assertEqual(len(only), 1)
        self.client.post("/repos/remove", data={"repo": only[0]})
        self.assertEqual(self._config().repos, only)


class SettingsTests(WebAppTestBase):
    def test_update_since_and_backend(self):
        r = self.client.post(
            "/settings", data={"since": "30 days ago", "backend": "codex", "until": ""}
        )
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/settings")
        cfg = self._config()
        self.assertEqual(cfg.since, "30 days ago")
        self.assertEqual(cfg.backend, "codex")
        self.assertIsNone(cfg.until)

    def test_update_with_until(self):
        self.client.post(
            "/settings",
            data={"since": "30 days ago", "backend": "kiro-cli", "until": "2026-11-01"},
        )
        self.assertEqual(self._config().until, "2026-11-01")

    def test_invalid_backend_is_ignored(self):
        self.client.post(
            "/settings", data={"since": "30 days ago", "backend": "bogus", "until": ""}
        )
        # Falls back to the current/default backend rather than persisting junk.
        self.assertIn(self._config().backend, ("kiro-cli", "codex", "cursor-agent"))


class CredentialTests(WebAppTestBase):
    def test_save_credentials_persists_without_exposing_values(self):
        r = self.client.post(
            "/credentials",
            data={
                "github_token": "ghp_secret123",
                "openai_api_key": "sk-openai",
                "cursor_api_key": "",
            },
        )
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/credentials")
        # Stored on disk with restrictive permissions.
        env_file = os.path.join(self.secrets_dir, "credentials.env")
        self.assertTrue(os.path.exists(env_file))
        self.assertEqual(oct(os.stat(env_file).st_mode & 0o777), "0o600")
        contents = open(env_file).read()
        self.assertIn("GITHUB_AUTH_TOKEN=ghp_secret123", contents)
        self.assertIn("OPENAI_API_KEY=sk-openai", contents)

        # Applied to the environment for the next run.
        self.assertEqual(os.environ.get("GITHUB_AUTH_TOKEN"), "ghp_secret123")

        # The credentials page shows status, never the secret value itself.
        page = self.client.get("/credentials").text
        self.assertNotIn("ghp_secret123", page)
        self.assertIn("set", page)  # a "✅ set" badge is present

    def test_kiro_status_shown_on_credentials_page(self):
        from health_checker_agent.backends import (
            KIRO_LOGGED_IN,
            KIRO_LOGGED_OUT,
            KIRO_NOT_INSTALLED,
        )

        cases = {
            KIRO_LOGGED_IN: "logged in",
            KIRO_LOGGED_OUT: "not logged in",
            KIRO_NOT_INSTALLED: "not installed",
        }
        for status_value, expected in cases.items():
            app = create_app(
                config_path=self.config_path,
                credentials_dir=self.secrets_dir,
                run_fleet_fn=self.fake_run_fleet,
                kiro_status_fn=lambda sv=status_value: sv,
            )
            page = TestClient(app).get("/credentials").text
            self.assertIn("Kiro CLI status:", page)
            self.assertIn(expected, page)

    def test_credentials_page_shows_device_login_command(self):
        page = self.client.get("/credentials").text
        self.assertIn(
            "docker compose exec health-checker kiro-cli login --use-device-flow",
            page,
        )
        # The note explains kiro-cli cannot use an API key.
        self.assertIn("device-code login", page)

    def tearDown(self):
        # Avoid leaking test credentials into other tests' environment.
        for var in ("GITHUB_AUTH_TOKEN", "OPENAI_API_KEY", "CURSOR_API_KEY"):
            os.environ.pop(var, None)


class MemoBrowseTests(WebAppTestBase):
    def test_list_and_view_memo(self):
        memo_path = os.path.join(self.output_dir, "octocat__Hello-World-memo.md")
        with open(memo_path, "w", encoding="utf-8") as fh:
            fh.write("# Hello memo\n\nSome content.\n")

        # Listed on the Memos & Presentation page (root).
        page = self.client.get("/").text
        self.assertIn("octocat__Hello-World-memo.md", page)

        # Viewable, with its content rendered.
        r = self.client.get("/memos/octocat__Hello-World-memo.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Hello memo", r.text)
        self.assertIn("Some content.", r.text)

    def test_missing_memo_404(self):
        r = self.client.get("/memos/does-not-exist-memo.md")
        self.assertEqual(r.status_code, 404)

    def test_memo_path_traversal_blocked(self):
        # Attempting to escape the output dir must not read arbitrary files.
        r = self.client.get("/memos/..%2F..%2Frepos.toml")
        self.assertIn(r.status_code, (403, 404))


class PptxDownloadTests(WebAppTestBase):
    def test_download_when_present(self):
        pptx_path = os.path.join(self.output_dir, "fleet-summary.pptx")
        with open(pptx_path, "wb") as fh:
            fh.write(b"PK\x03\x04 fake pptx bytes")
        r = self.client.get("/download/pptx")
        self.assertEqual(r.status_code, 200)
        self.assertIn("presentationml", r.headers["content-type"])
        self.assertTrue(r.content.startswith(b"PK"))

    def test_download_404_when_absent(self):
        r = self.client.get("/download/pptx")
        self.assertEqual(r.status_code, 404)


class RunAnalysisTests(WebAppTestBase):
    def test_run_triggers_fleet(self):
        r = self.client.post("/run", data={"force": "1"})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/run")
        # The run happens on a background thread; wait briefly for it.
        for _ in range(50):
            if self.run_calls:
                break
            time.sleep(0.02)
        self.assertEqual(len(self.run_calls), 1)
        call = self.run_calls[0]
        self.assertTrue(call["force"])
        self.assertTrue(call["pptx"])  # UI always builds the deck
        self.assertIn("metal3-io/metal3-dev-env", call["config"].repos)

    def test_run_without_force(self):
        self.client.post("/run", data={})
        for _ in range(50):
            if self.run_calls:
                break
            time.sleep(0.02)
        self.assertEqual(len(self.run_calls), 1)
        self.assertFalse(self.run_calls[0]["force"])

    def test_run_failure_surfaced_in_status(self):
        def boom(config, *, force=False, pptx=False):
            raise RuntimeError("backend not logged in")

        app = create_app(
            config_path=self.config_path,
            credentials_dir=self.secrets_dir,
            run_fleet_fn=boom,
        )
        client = TestClient(app, follow_redirects=False)
        client.post("/run", data={})
        # Poll the status endpoint until the background run finishes.
        for _ in range(50):
            body = client.get("/status").json()
            if not body["running"] and body["finished_at"]:
                break
            time.sleep(0.02)
        self.assertFalse(body["ok"])
        self.assertIn("backend not logged in", body["message"])


if __name__ == "__main__":
    unittest.main()
