"""FastAPI web UI for the Project Health Checker.

A small browser interface that lets a user, without touching the CLI:

- edit the repositories to analyse (add/remove, stored in ``repos.toml``),
- enter credentials for the AI tooling and a GitHub token,
- browse the generated memos,
- download the PowerPoint deck,
- and (re-)run the analysis.

The app is created with :func:`create_app`, which takes the paths it works on so
tests can point it at temporary files. The analysis runs in a background thread
so a long run does not block the request; a small in-memory status object lets
the UI show whether a run is in progress and its last result.

Rendering is done with inline HTML (no template files) to keep the module
self-contained and easy to test.
"""

from __future__ import annotations

import html
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .backends import SUPPORTED_BACKENDS
from .config import (
    Config,
    ConfigError,
    load_config,
    parse_config,
    save_config,
    with_repos,
)
from .credentials import CREDENTIAL_ENV_VARS, CredentialStore

DEFAULT_CONFIG_PATH = "repos.toml"
# Directory where credentials (and other persisted secrets) live. Mounted as a
# volume in the container so it survives restarts.
DEFAULT_CREDENTIALS_DIR = "secrets"


@dataclass
class RunStatus:
    """In-memory status of the most recent / current analysis run."""

    running: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    message: str = "No analysis has run yet."
    ok: bool = True
    lock: threading.Lock = field(default_factory=threading.Lock)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def create_app(
    *,
    config_path: str = DEFAULT_CONFIG_PATH,
    credentials_dir: str = DEFAULT_CREDENTIALS_DIR,
    run_fleet_fn=None,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config_path: Path to the ``repos.toml`` the UI reads and writes.
        credentials_dir: Directory for the persisted credential store.
        run_fleet_fn: Injectable analysis runner (defaults to
            :func:`agent.run_fleet`). Tests pass a stub.
    """
    if run_fleet_fn is None:
        from .agent import run_fleet as run_fleet_fn  # lazy to ease testing

    creds = CredentialStore(credentials_dir)
    # Apply any previously-stored credentials to the environment on startup.
    creds.apply()

    status = RunStatus()
    app = FastAPI(title="Project Health Checker")

    # --- config helpers -------------------------------------------------

    def _read_config() -> Config:
        if os.path.exists(config_path):
            return load_config(config_path)
        # A sensible empty-ish default when no config exists yet.
        return parse_config('since = "90 days ago"\nrepos = ["metal3-io/metal3-dev-env"]\n')

    def _output_dir() -> str:
        try:
            return _read_config().output_dir
        except ConfigError:
            return "output"

    # --- analysis runner ------------------------------------------------

    def _run_analysis(force: bool) -> None:
        with status.lock:
            if status.running:
                return
            status.running = True
            status.started_at = _now()
            status.finished_at = None
            status.message = "Analysis in progress…"
            status.ok = True

        def worker() -> None:
            try:
                config = _read_config()
                creds.apply()
                run_fleet_fn(config, force=force, pptx=True)
                msg = "Analysis complete."
                ok = True
            except Exception as exc:  # noqa: BLE001 - report any failure to the UI
                msg = f"Analysis failed: {exc}"
                ok = False
            with status.lock:
                status.running = False
                status.finished_at = _now()
                status.message = msg
                status.ok = ok

        threading.Thread(target=worker, daemon=True).start()

    # --- routes ---------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_index(_read_config_safe(), creds.status(), status, _list_memos(_output_dir()), _pptx_exists(_output_dir()))

    def _read_config_safe():
        try:
            return _read_config()
        except ConfigError:
            return None

    @app.post("/repos/add")
    def add_repo(repo: str = Form(...)):
        repo = repo.strip()
        config = _read_config()
        if repo and repo not in config.repos:
            try:
                save_config(config_path, with_repos(config, [*config.repos, repo]))
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        return RedirectResponse("/", status_code=303)

    @app.post("/repos/remove")
    def remove_repo(repo: str = Form(...)):
        repo = repo.strip()
        config = _read_config()
        remaining = [r for r in config.repos if r != repo]
        if remaining and remaining != config.repos:
            save_config(config_path, with_repos(config, remaining))
        return RedirectResponse("/", status_code=303)

    @app.post("/settings")
    def update_settings(
        since: str = Form(...),
        backend: str = Form(...),
        until: str = Form(""),
    ):
        config = _read_config()
        from dataclasses import replace

        new = replace(
            config,
            since=since.strip() or config.since,
            backend=backend if backend in SUPPORTED_BACKENDS else config.backend,
            until=(until.strip() or None),
        )
        try:
            save_config(config_path, new)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return RedirectResponse("/", status_code=303)

    @app.post("/credentials")
    def update_credentials(
        github_token: str = Form(""),
        openai_api_key: str = Form(""),
        cursor_api_key: str = Form(""),
    ):
        creds.save(
            {
                "github_token": github_token,
                "openai_api_key": openai_api_key,
                "cursor_api_key": cursor_api_key,
            }
        )
        return RedirectResponse("/", status_code=303)

    @app.post("/run")
    def run(force: str = Form("")):
        _run_analysis(force=bool(force))
        return RedirectResponse("/", status_code=303)

    @app.get("/status")
    def get_status():
        with status.lock:
            return {
                "running": status.running,
                "started_at": status.started_at,
                "finished_at": status.finished_at,
                "message": status.message,
                "ok": status.ok,
            }

    @app.get("/memos/{name}", response_class=HTMLResponse)
    def view_memo(name: str) -> str:
        path = _safe_output_path(_output_dir(), name)
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Memo not found")
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        return _render_memo(name, content)

    @app.get("/download/pptx")
    def download_pptx():
        path = os.path.join(_output_dir(), "fleet-summary.pptx")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="No presentation available yet")
        return FileResponse(
            path,
            media_type=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            filename="fleet-summary.pptx",
        )

    return app


# --- filesystem helpers (module-level, reused by routes) ----------------


def _safe_output_path(output_dir: str, name: str) -> Optional[str]:
    """Resolve ``name`` inside ``output_dir``; return None if it escapes."""
    base = os.path.abspath(output_dir)
    target = os.path.abspath(os.path.join(base, name))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _list_memos(output_dir: str):
    """Return the memo filenames in ``output_dir`` (``*-memo.md``), sorted."""
    if not os.path.isdir(output_dir):
        return []
    return sorted(
        f for f in os.listdir(output_dir) if f.endswith("-memo.md")
    )


def _pptx_exists(output_dir: str) -> bool:
    return os.path.exists(os.path.join(output_dir, "fleet-summary.pptx"))


# --- rendering ----------------------------------------------------------


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _render_index(config, cred_status, status: RunStatus, memos, pptx_ready) -> str:
    backends_opts = "".join(
        f'<option value="{_esc(b)}"{" selected" if config and b == config.backend else ""}>{_esc(b)}</option>'
        for b in SUPPORTED_BACKENDS
    )

    repo_rows = ""
    if config and config.repos:
        for r in config.repos:
            repo_rows += (
                f'<li><span>{_esc(r)}</span>'
                f'<form method="post" action="/repos/remove" style="display:inline">'
                f'<input type="hidden" name="repo" value="{_esc(r)}">'
                f'<button type="submit">Remove</button></form></li>'
            )
    else:
        repo_rows = "<li><em>No repositories configured.</em></li>"

    memo_rows = ""
    if memos:
        for m in memos:
            memo_rows += f'<li><a href="/memos/{_esc(m)}">{_esc(m)}</a></li>'
    else:
        memo_rows = "<li><em>No memos yet. Run the analysis.</em></li>"

    def cred_badge(key: str) -> str:
        return "✅ set" if cred_status.get(key) else "— not set"

    since_val = _esc(config.since) if config else ""
    until_val = _esc(config.until) if config and config.until else ""
    run_badge = "running…" if status.running else ("ok" if status.ok else "error")
    pptx_section = (
        '<a href="/download/pptx"><button>Download fleet-summary.pptx</button></a>'
        if pptx_ready
        else "<em>No presentation generated yet.</em>"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project Health Checker</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
 h1 {{ font-size: 1.6rem; }} h2 {{ margin-top: 2rem; font-size: 1.15rem; border-bottom: 1px solid #ddd; padding-bottom: .3rem; }}
 ul {{ list-style: none; padding: 0; }} li {{ padding: .25rem 0; display: flex; justify-content: space-between; align-items: center; }}
 button {{ cursor: pointer; }} input, select {{ padding: .3rem; }}
 .status {{ padding: .6rem .8rem; border-radius: 6px; background: #f4f5f7; border: 1px solid #ddd; }}
 .row {{ display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }}
 label {{ display: inline-block; min-width: 7rem; }}
</style></head>
<body>
<h1>Project Health Checker</h1>

<div class="status"><strong>Analysis status ({_esc(run_badge)}):</strong> {_esc(status.message)}
{f'<br>started {_esc(status.started_at)}' if status.started_at else ''}
{f' · finished {_esc(status.finished_at)}' if status.finished_at else ''}</div>

<h2>Repositories</h2>
<ul>{repo_rows}</ul>
<form method="post" action="/repos/add" class="row">
  <input type="text" name="repo" placeholder="owner/name" required>
  <button type="submit">Add repository</button>
</form>

<h2>Settings</h2>
<form method="post" action="/settings" class="row">
  <div><label>Since</label><input type="text" name="since" value="{since_val}" required></div>
  <div><label>Until</label><input type="text" name="until" value="{until_val}" placeholder="(optional)"></div>
  <div><label>Backend</label><select name="backend">{backends_opts}</select></div>
  <button type="submit">Save settings</button>
</form>

<h2>Credentials</h2>
<p>GitHub token: {cred_badge('github_token')} &middot;
   OpenAI (codex): {cred_badge('openai_api_key')} &middot;
   Cursor: {cred_badge('cursor_api_key')}</p>
<form method="post" action="/credentials">
  <div class="row"><label>GitHub token</label><input type="password" name="github_token" placeholder="leave blank to keep"></div>
  <div class="row"><label>OpenAI API key</label><input type="password" name="openai_api_key" placeholder="leave blank to keep"></div>
  <div class="row"><label>Cursor API key</label><input type="password" name="cursor_api_key" placeholder="leave blank to keep"></div>
  <button type="submit">Save credentials</button>
</form>

<h2>Run analysis</h2>
<form method="post" action="/run" class="row">
  <label><input type="checkbox" name="force" value="1"> Force re-analysis</label>
  <button type="submit"{' disabled' if status.running else ''}>Run now</button>
</form>

<h2>Memos</h2>
<ul>{memo_rows}</ul>

<h2>Presentation</h2>
<p>{pptx_section}</p>

</body></html>"""


def _render_memo(name: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(name)}</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; }}
 pre {{ white-space: pre-wrap; word-wrap: break-word; background: #f7f8fa; padding: 1rem; border-radius: 6px; }}
 a {{ display: inline-block; margin-bottom: 1rem; }}
</style></head>
<body>
<a href="/">&larr; Back</a>
<h1>{_esc(name)}</h1>
<pre>{_esc(content)}</pre>
</body></html>"""
