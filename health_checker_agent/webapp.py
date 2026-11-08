"""FastAPI web UI for the Project Health Checker.

A small browser interface that lets a user, without touching the CLI:

- edit the repositories to analyse (add/remove, stored in ``repos.toml``),
- adjust the analysis settings,
- enter credentials for the AI tooling and a GitHub token,
- (re-)run the analysis,
- browse the generated memos and download the PowerPoint deck.

Each capability lives on its own page, linked from a navigation bar:

- ``/``             Memos & Presentation (default)
- ``/repositories`` Repositories
- ``/settings``     Settings
- ``/credentials``  Credentials
- ``/run``          Run analysis (the only page that shows the run status)

The app is created with :func:`create_app`, which takes the paths it works on so
tests can point it at temporary files. The analysis runs in a background thread
so a long run does not block the request; a small in-memory status object lets
the Run analysis page show whether a run is in progress and its last result.

Rendering is done with inline HTML (no template files) to keep the module
self-contained and easy to test.
"""

from __future__ import annotations

import html
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .backends import (
    KIRO_LOGGED_IN,
    KIRO_LOGGED_OUT,
    KIRO_NOT_INSTALLED,
    SUPPORTED_BACKENDS,
    kiro_login_status,
)
from .config import (
    Config,
    ConfigError,
    load_config,
    parse_config,
    save_config,
    with_repos,
)
from .credentials import CredentialStore

DEFAULT_CONFIG_PATH = "repos.toml"

# Navigation bar entries: (path, label). Order drives the nav bar; "/" is the
# default landing page (Memos & Presentation).
_NAV = [
    ("/", "Memos & Presentation"),
    ("/repositories", "Repositories"),
    ("/settings", "Settings"),
    ("/credentials", "Credentials"),
    ("/run", "Run analysis"),
]


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
    run_fleet_fn=None,
    kiro_status_fn=None,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config_path: Path to the ``repos.toml`` the UI reads and writes.
        run_fleet_fn: Injectable analysis runner (defaults to
            :func:`agent.run_fleet`). Tests pass a stub.
        kiro_status_fn: Injectable kiro-cli login-status probe (defaults to
            :func:`backends.kiro_login_status`). Tests pass a stub so they do
            not shell out.
    """
    if run_fleet_fn is None:
        from .agent import run_fleet as run_fleet_fn  # lazy to ease testing
    if kiro_status_fn is None:
        kiro_status_fn = kiro_login_status

    # Credentials live only in the process environment, never on disk.
    creds = CredentialStore()

    status = RunStatus()
    app = FastAPI(title="Project Health Checker")

    # --- config helpers -------------------------------------------------

    def _read_config() -> Config:
        if os.path.exists(config_path):
            return load_config(config_path)
        # A sensible empty-ish default when no config exists yet.
        return parse_config('since = "90 days ago"\nrepos = ["metal3-io/metal3-dev-env"]\n')

    def _read_config_safe():
        try:
            return _read_config()
        except ConfigError:
            return None

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

    # --- pages ----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def memos_page() -> str:
        output_dir = _output_dir()
        return _render_memos(
            "/",
            _list_memos(output_dir),
            _pptx_exists(output_dir),
            _fleet_report_exists(output_dir),
        )

    @app.get("/repositories", response_class=HTMLResponse)
    def repositories_page() -> str:
        return _render_repositories("/repositories", _read_config_safe())

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page() -> str:
        return _render_settings("/settings", _read_config_safe())

    @app.get("/credentials", response_class=HTMLResponse)
    def credentials_page() -> str:
        return _render_credentials(
            "/credentials", creds.status(), kiro_status_fn()
        )

    @app.get("/run", response_class=HTMLResponse)
    def run_page() -> str:
        return _render_run("/run", status)

    # --- actions (POST → redirect back to the owning page) --------------

    @app.post("/repos/add")
    def add_repo(repo: str = Form(...)):
        repo = repo.strip()
        config = _read_config()
        if repo and repo not in config.repos:
            try:
                save_config(config_path, with_repos(config, [*config.repos, repo]))
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        return RedirectResponse("/repositories", status_code=303)

    @app.post("/repos/remove")
    def remove_repo(repo: str = Form(...)):
        repo = repo.strip()
        config = _read_config()
        remaining = [r for r in config.repos if r != repo]
        if remaining and remaining != config.repos:
            save_config(config_path, with_repos(config, remaining))
        return RedirectResponse("/repositories", status_code=303)

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
        return RedirectResponse("/settings", status_code=303)

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
        return RedirectResponse("/credentials", status_code=303)

    @app.post("/credentials/clear")
    def clear_credential(key: str = Form(...)):
        creds.clear([key.strip()])
        return RedirectResponse("/credentials", status_code=303)

    @app.post("/run")
    def run(force: str = Form("")):
        _run_analysis(force=bool(force))
        return RedirectResponse("/run", status_code=303)

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
        return _render_memo("/", name, content)

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
    return sorted(f for f in os.listdir(output_dir) if f.endswith("-memo.md"))


def _pptx_exists(output_dir: str) -> bool:
    return os.path.exists(os.path.join(output_dir, "fleet-summary.pptx"))


FLEET_REPORT_NAME = "fleet-report.md"


def _fleet_report_exists(output_dir: str) -> bool:
    return os.path.exists(os.path.join(output_dir, FLEET_REPORT_NAME))


# --- rendering ----------------------------------------------------------


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


_STYLE = """
 body { font-family: system-ui, sans-serif; max-width: 860px; margin: 0 auto 2rem; padding: 0 1rem; color: #222; }
 h1 { font-size: 1.6rem; } h2 { margin-top: 1.5rem; font-size: 1.15rem; border-bottom: 1px solid #ddd; padding-bottom: .3rem; }
 ul { list-style: none; padding: 0; } li { padding: .25rem 0; display: flex; justify-content: space-between; align-items: center; }
 button { cursor: pointer; } input, select { padding: .3rem; }
 .status { padding: .6rem .8rem; border-radius: 6px; background: #f4f5f7; border: 1px solid #ddd; }
 .status.error { background: #f6ecec; border-color: #e0b4b4; }
 .status.running { background: #eef3f8; border-color: #bcd3e6; }
 .row { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
 .highlight { padding: .7rem .9rem; border-radius: 6px; background: #eef3f8; border: 1px solid #bcd3e6; }
 .highlight a { font-size: 1.05rem; }
 label { display: inline-block; min-width: 7rem; }
 pre { white-space: pre-wrap; word-wrap: break-word; background: #f7f8fa; padding: .6rem .8rem; border-radius: 6px; border: 1px solid #e3e6ea; }
 nav { background: #1f2a37; margin-bottom: 1.5rem; border-radius: 0 0 6px 6px; }
 nav .inner { max-width: 860px; margin: 0 auto; padding: 0 1rem; display: flex; gap: .25rem; flex-wrap: wrap; }
 nav a { color: #cdd5df; text-decoration: none; padding: .7rem .8rem; display: inline-block; font-size: .95rem; }
 nav a:hover { color: #fff; } nav a.active { color: #fff; border-bottom: 3px solid #4f93ce; font-weight: 600; }
"""


def _nav(active_path: str) -> str:
    links = "".join(
        f'<a href="{_esc(path)}"{" class=\"active\"" if path == active_path else ""}>{_esc(label)}</a>'
        for path, label in _NAV
    )
    return f'<nav><div class="inner">{links}</div></nav>'


def _page(title: str, active_path: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} · Project Health Checker</title>
<style>{_STYLE}</style></head>
<body>
{_nav(active_path)}
<main>
{body}
</main>
</body></html>"""


def _render_memos(active_path: str, memos, pptx_ready, fleet_report_ready=False) -> str:
    # The fleet report is the roll-up that links to every per-repo memo, so it
    # gets a highlighted section of its own above the per-repo list.
    if fleet_report_ready:
        fleet_section = (
            f'<div class="highlight">'
            f'<a href="/memos/{_esc(FLEET_REPORT_NAME)}"><strong>'
            f"\U0001f4cb Fleet report</strong></a> — the fleet-wide roll-up "
            f"linking every project's memo.</div>"
        )
    else:
        fleet_section = (
            "<p><em>No fleet report yet. Run the analysis.</em></p>"
        )

    if memos:
        memo_rows = "".join(
            f'<li><a href="/memos/{_esc(m)}">{_esc(m)}</a></li>' for m in memos
        )
    else:
        memo_rows = "<li><em>No per-project memos yet. Run the analysis.</em></li>"

    pptx_section = (
        '<a href="/download/pptx"><button>Download fleet-summary.pptx</button></a>'
        if pptx_ready
        else "<em>No presentation generated yet. Run the analysis.</em>"
    )

    body = f"""<h1>Memos &amp; Presentation</h1>
<h2>Fleet report</h2>
{fleet_section}
<h2>Project memos</h2>
<ul>{memo_rows}</ul>
<h2>Presentation</h2>
<p>{pptx_section}</p>"""
    return _page("Memos & Presentation", active_path, body)


def _render_repositories(active_path: str, config) -> str:
    if config and config.repos:
        repo_rows = "".join(
            f'<li><span>{_esc(r)}</span>'
            f'<form method="post" action="/repos/remove" style="display:inline">'
            f'<input type="hidden" name="repo" value="{_esc(r)}">'
            f'<button type="submit">Remove</button></form></li>'
            for r in config.repos
        )
    else:
        repo_rows = "<li><em>No repositories configured.</em></li>"

    body = f"""<h1>Repositories</h1>
<p>Repositories analysed on each run, in <code>owner/name</code> form.</p>
<ul>{repo_rows}</ul>
<form method="post" action="/repos/add" class="row">
  <input type="text" name="repo" placeholder="owner/name" required>
  <button type="submit">Add repository</button>
</form>"""
    return _page("Repositories", active_path, body)


def _render_settings(active_path: str, config) -> str:
    backends_opts = "".join(
        f'<option value="{_esc(b)}"{" selected" if config and b == config.backend else ""}>{_esc(b)}</option>'
        for b in SUPPORTED_BACKENDS
    )
    since_val = _esc(config.since) if config else ""
    until_val = _esc(config.until) if config and config.until else ""

    body = f"""<h1>Settings</h1>
<form method="post" action="/settings" class="row">
  <div><label>Since</label><input type="text" name="since" value="{since_val}" placeholder="e.g. 90 days ago" required></div>
  <div><label>Until</label><input type="text" name="until" value="{until_val}" placeholder="(optional)"></div>
  <div><label>Backend</label><select name="backend">{backends_opts}</select></div>
  <button type="submit">Save settings</button>
</form>
<p><small>The backend is the AI CLI used to write the memos.</small></p>"""
    return _page("Settings", active_path, body)


_KIRO_STATUS_LABEL = {
    KIRO_LOGGED_IN: "✅ logged in",
    KIRO_LOGGED_OUT: "— not logged in",
    KIRO_NOT_INSTALLED: "— not installed",
}


def _render_credentials(active_path: str, cred_status, kiro_status: str) -> str:
    def badge(key: str) -> str:
        return "✅ set" if cred_status.get(key) else "— not set"

    def clear_button(key: str) -> str:
        if not cred_status.get(key):
            return ""
        return (
            f'<form method="post" action="/credentials/clear" style="display:inline">'
            f'<input type="hidden" name="key" value="{_esc(key)}">'
            f'<button type="submit">Clear</button></form>'
        )

    kiro_label = _KIRO_STATUS_LABEL.get(kiro_status, "— unknown")

    body = f"""<h1>Credentials</h1>
<p>GitHub token: {badge('github_token')} &middot;
   OpenAI (codex): {badge('openai_api_key')} &middot;
   Cursor: {badge('cursor_api_key')}</p>
<form method="post" action="/credentials">
  <div class="row"><label>GitHub token</label><input type="password" name="github_token" placeholder="leave blank to keep"> {clear_button('github_token')}</div>
  <div class="row"><label>OpenAI API key</label><input type="password" name="openai_api_key" placeholder="leave blank to keep"> {clear_button('openai_api_key')}</div>
  <div class="row"><label>Cursor API key</label><input type="password" name="cursor_api_key" placeholder="leave blank to keep"> {clear_button('cursor_api_key')}</div>
  <button type="submit">Save credentials</button>
</form>
<p><small><strong>Credentials are kept only in memory, never written to
disk.</strong> They live in the running server's environment, so you must
re-enter them after every restart. Leave a field blank to keep its current
value; use <em>Clear</em> to remove one. (Values exported in the shell before
launch are used automatically.)</small></p>

<h2>Kiro CLI login</h2>
<p>Kiro CLI status: {_esc(kiro_label)}</p>
<p><small>Unlike codex and Cursor, <code>kiro-cli</code> cannot authenticate
with an API key — it uses an interactive device-code login that this web form
cannot drive. After the container is started, complete it from a terminal:</small></p>
<pre>docker compose exec health-checker kiro-cli login --use-device-flow</pre>
<p><small>Follow the printed URL and code to finish. Reload this page to refresh
the status.</small></p>"""
    return _page("Credentials", active_path, body)


def _render_run(active_path: str, status: RunStatus) -> str:
    run_badge = "running…" if status.running else ("ok" if status.ok else "error")
    status_class = "status running" if status.running else ("status" if status.ok else "status error")
    timing = ""
    if status.started_at:
        timing += f"<br>started {_esc(status.started_at)}"
    if status.finished_at:
        timing += f" · finished {_esc(status.finished_at)}"

    body = f"""<h1>Run analysis</h1>
<div class="{status_class}"><strong>Analysis status ({_esc(run_badge)}):</strong> {_esc(status.message)}{timing}</div>
<form method="post" action="/run" class="row" style="margin-top:1rem">
  <label><input type="checkbox" name="force" value="1"> Force re-analysis</label>
  <button type="submit"{' disabled' if status.running else ''}>Run now</button>
</form>
<p><small>Runs in the background. Reload this page to refresh the status, or see
the live JSON at <a href="/status">/status</a>.</small></p>"""
    return _page("Run analysis", active_path, body)


# Markdown link to a sibling .md file, e.g. "[memo](owner__name-memo.md)".
# Matched against the HTML-escaped content, so the target is a bare relative
# filename (no scheme, no slash) ending in .md.
_LOCAL_MD_LINK = re.compile(r"\[([^\]]+)\]\((?!https?:|/)([^)\s]+\.md)\)")


def _linkify_local_md(escaped: str) -> str:
    """Turn ``[text](local.md)`` references into clickable ``/memos/`` links.

    Operates on already-HTML-escaped text. Only sibling ``.md`` files are
    linked (not absolute URLs), so the fleet report's links to each per-repo
    memo become navigable from the browser.
    """

    def repl(m: re.Match) -> str:
        text, target = m.group(1), m.group(2)
        return f'<a href="/memos/{_esc(target)}">{text}</a>'

    return _LOCAL_MD_LINK.sub(repl, escaped)


def _render_memo(active_path: str, name: str, content: str) -> str:
    # Memo view keeps the nav; it belongs under the Memos & Presentation tab.
    # Make local markdown links (notably the fleet report's per-repo memo links)
    # clickable, while leaving all other text escaped.
    rendered = _linkify_local_md(_esc(content))
    body = f"""<p><a href="/">&larr; Back to memos</a></p>
<h1>{_esc(name)}</h1>
<pre>{rendered}</pre>"""
    return _page(name, active_path, body)
