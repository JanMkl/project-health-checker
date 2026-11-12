# Project Health Checker

`health-checker-agent` analyses one or many GitHub projects' git activity,
issues, and pull requests, asks an AI coding CLI to write a per-project
management memo (in Markdown), and rolls everything up into a single fleet
report grouping projects by how much management attention they need. The memo
CLI is pluggable — `kiro-cli` (default), `codex`, or `cursor-agent` — selected
with `--backend` or the `backend` config key.

The access policy for the agent is defined in [AGENTS.md](AGENTS.md).

## How it works

For each repository, orchestrated by `run_repo`:

1. **Clone tool** (`clone_tool.py`) — clones the repo into the working directory
   (or fetches/fast-forwards an existing clone) using `git`.
2. **Git log tool** (`git_log_tool.py`) — runs `git log` over a time window and
   collects commits (author, date, subject).
3. **Issues tool** (`issues_tool.py`) — fetches both open and closed issues via
   `curl` against the GitHub REST API.
4. **Pull requests tool** (`pulls_tool.py`) — fetches both open and closed
   (including merged) pull requests.
5. **Adopters tool** (`adopters_tool.py`) — looks for the project's
   `ADOPTERS.md`. Following the CNCF convention, this file usually lives in the
   owner's central community repo (e.g. `metal3-io/community/ADOPTERS.md`)
   rather than the project repo, so the tool probes `<owner>/community`,
   `<owner>/.github`, and the project repo, using the first one found.
6. **Security tool** (`security_tool.py`) — looks for a `SECURITY.md` (repo
   root, `.github/`, or `docs/`) or `SECURITY_CONTACTS` file, including the
   org-level `<owner>/.github` default. Its presence signals a documented
   security disclosure/response process; its content lets the memo assess
   whether that process follows responsible-disclosure best practices.
7. **Owners tool** (`owners_tool.py`) — looks for an `OWNERS` file (no `.md`
   extension) in the project repo root or `.github/`. It lists the project's
   reviewers and approvers/maintainers, so its presence signals transparency
   about who holds merge authority. It is project-specific, so only the project
   repo is probed.
8. **Health classification** (`health.py`) — deterministically sorts the repo
   into `healthy`, `attention`, or `investigate` from the collected counts.
9. **Memo generation** (`memo.py`) — builds a prompt from the commits, issues,
   pull requests, adopters, security policy, and owners, and pipes it to the
   selected AI CLI backend (`backends.py`) for the Markdown memo (which includes
   Adopters, Security Process, and Governance (Owners) sections).

Across all repos, `run_fleet` writes `output/fleet-report.md` grouping projects
into: requires management attention, needs investigation / keep an eye on, and
healthy (no attention needed).

The issues and pull requests (open and closed) let the memo identify active
contributors and community members by cross-referencing commit authors with
issue and PR authors, since commit authorship alone understates who is active.
Shared GitHub API plumbing (auth, redirects, error handling) lives in
`github_api.py`.

### Skipping unchanged analyses

Re-running the AI CLI for every repo is expensive. After each analysis the agent
stores an input *fingerprint* (commit count and latest commit, plus open/closed
issue and PR counts and newest timestamps) next to the memo. On a later run, if
the fingerprint is unchanged the existing memo is reused and the AI CLI is not
called again. Use `--force` to re-analyse regardless.

All memos, reports, state files, and repository clones are written under the
`output/` directory, which is the only location the agent is permitted to write
to.

## Web UI (Docker)

A browser interface is available for driving the whole workflow without the CLI.
It bundles all three AI CLIs (kiro-cli, codex, and cursor-agent) in a container
and serves a dashboard on port 8080.

```bash
docker compose up
```

Then open <http://localhost:8080>. A navigation bar links the pages:

- **Memos & Presentation** (the default page) — browse the generated memos
  (rendered from Markdown to formatted HTML) and download the PowerPoint deck.
- **Repositories** — add/remove the repositories to analyse (persisted to
  `repos.toml`).
- **Settings** — set the analysis window (`since`/`until`) and the backend.
- **Credentials** — enter the GitHub token and AI-tool API keys (kept only in
  memory, never shown back in the browser or written to disk).
- **Run analysis** — (re-)run the analysis; it runs in the background and this
  page shows the status.

`docker compose up` bind-mounts `repos.toml` and `output/` so your config and
results persist on the host across restarts. Credentials are deliberately not
persisted — see below.

### Image size: skipping kiro-cli

All three CLIs are installed by default. The `kiro-cli` binary is large
(~400 MB) and dominates the image size; if you only use the `codex` or
`cursor-agent` backends you can skip it:

```bash
INSTALL_KIRO_CLI=false docker compose build
```

### Authentication (credentials are never stored on disk)

For safety, secrets are kept only in the running process's memory — nothing is
written to disk. This means **you re-enter credentials after every restart**,
but they can never leak from a file. Two paths set them:

1. **GitHub token and the codex (`OPENAI_API_KEY`) / cursor (`CURSOR_API_KEY`)
   keys** — enter them on the Credentials page (or `export` them in the shell
   before launch, which the app picks up automatically). They are held in the
   process environment and cleared when the container stops.
2. **kiro-cli** — it can't use an API key; it uses a device-code login. After
   the container is up, run it once from a terminal:

   ```bash
   docker compose exec health-checker kiro-cli login --use-device-flow
   ```

   (Follow the printed URL/code to authenticate.) `codex` similarly supports
   `codex login --device-auth`.

The Credentials page shows the current kiro-cli login status (logged in / not
logged in / not installed) and the command above, so you can tell at a glance
whether the login still needs doing. Because the kiro-cli login is not
persisted either, it must be redone after a restart.

### Generate on the host, serve with the container

You don't have to run the analysis inside the container. Because the container
and the host share the same `output/` directory (it's bind-mounted), you can
split the two jobs:

- **Generate the reports on the host** with the CLI, where your credentials and
  AI-CLI logins already live in your shell — no need to re-enter anything in the
  browser:

  ```bash
  # one-off: install the package (CLI only needs the base deps)
  .venv/bin/python -m pip install -e .

  # run the full analysis and build the deck; writes into output/
  .venv/bin/python -m health_checker_agent --config repos.toml --pptx
  ```

- **Use the container only to browse and download** the results. Everything the
  host wrote to `output/` shows up on the Memos & Presentation page, so the
  container becomes a lightweight viewer:

  ```bash
  docker compose up
  ```

This is handy when you'd rather keep credential setup on your own machine (where
`kiro-cli login`, `OPENAI_API_KEY`, etc. are already configured) while still
getting easy browser access to the memos, fleet report, and PowerPoint deck. The
container's **Run analysis** page still works too; this just gives you the option
not to use it.

### Running the UI without Docker

```bash
.venv/bin/python -m pip install -e .[web]
.venv/bin/python -m health_checker_agent.server   # serves on 0.0.0.0:8080
```

## Requirements

- Python 3.10+
- `git` and `curl` available on your `PATH`
- One AI coding CLI on your `PATH`, matching the backend you select:
  `kiro-cli` (default), `codex`, or `cursor-agent`
  (these are the only shell commands the agent is allowed to run)

## Setup

```bash
# Create and populate a virtual environment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then create your configuration. `repos.toml` holds your personal list of
repositories and is intentionally **not tracked in git** (it's in
`.gitignore`), so you must create it before the first run by copying the
provided template:

```bash
cp repos.toml.example repos.toml
# then edit repos.toml to list the repositories you want to analyse
```

See [`repos.toml.example`](repos.toml.example) for all available settings. (The
Docker image seeds `repos.toml` from this template automatically on first start
if one isn't mounted.)

## GitHub token (optional but recommended)

Unauthenticated GitHub API requests are rate-limited to 60/hour. If you export a
token, the agent sends it as a Bearer token and the limit rises to 5000/hour.

```bash
export GITHUB_AUTH_TOKEN=ghp_your_token_here
```

The token is read from the environment only. It is never a command-line flag, so
it won't leak into your shell history or process listings.

## Usage

The agent clones the repositories for you, so you no longer pass a local path.

### Many repositories (config file)

Create a TOML config (see [`repos.toml.example`](repos.toml.example)):

```toml
since = "90 days ago"
work_dir = "output/repos"
output_dir = "output"
repos = [
    "metal3-io/metal3-dev-env",
    "metal3-io/baremetal-operator",
    "metal3-io/ip-address-manager",
]
```

Then run:

```bash
.venv/bin/python -m health_checker_agent --config repos.toml
```

This clones each repo under `output/repos/`, writes one memo per repo
(`output/<owner>__<name>-memo.md`), and a roll-up at `output/fleet-report.md`.

### A single repository

```bash
.venv/bin/python -m health_checker_agent \
    --repo metal3-io/metal3-dev-env \
    --since "30 days ago"
```

### Options

| Flag           | Required            | Description                                                      |
| -------------- | ------------------- | ---------------------------------------------------------------- |
| `--config`     | one of config/repo  | Path to a TOML config listing repos and settings.                |
| `--repo`       | one of config/repo  | Analyse a single repository in `owner/name` form.                |
| `--since`      | with `--repo`       | Start of the period, e.g. `"30 days ago"`; overrides config.     |
| `--until`      | no                  | Optional end of the period.                                      |
| `--work-dir`   | no                  | Directory to clone repos into (default: `output/repos`).         |
| `--output-dir` | no                  | Directory for memos and reports (default: `output`).             |
| `--backend`    | no                  | AI CLI to write memos: `kiro-cli` (default), `codex`, or `cursor-agent`; overrides config. |
| `--force`      | no                  | Re-run analysis even if the inputs have not changed.             |
| `--pptx`       | no                  | Also write a PowerPoint deck of the findings (see below).        |

## Choosing an AI CLI backend

The memos are written by an AI coding CLI. Pick whichever you have installed:

| Backend        | Executable                  | Invocation (non-interactive)              |
| -------------- | --------------------------- | ----------------------------------------- |
| `kiro-cli`     | `kiro-cli`                  | `kiro-cli chat --no-interactive --trust-all-tools` |
| `codex`        | `codex`                     | `codex exec`                              |
| `cursor-agent` | `cursor-agent` or `agent`   | `cursor-agent --print --output-format text --trust` |

The prompt is always fed on stdin (so large repositories don't hit the OS
argument-length limit). `kiro-cli` and `cursor-agent` print the memo to stdout;
`codex exec` prints an event log, so the agent captures its final message via
`--output-last-message` instead. Cursor installs its CLI under both
`cursor-agent` and the bare name `agent` — whichever is on your `PATH` is used.
Select a backend per run with `--backend`, or set a default in the config:

```toml
# repos.toml
backend = "codex"
```

```bash
.venv/bin/python -m health_checker_agent --config repos.toml --backend cursor-agent
```

Only the executable for the selected backend needs to be on your `PATH`; the
other backends are not required.

### Authenticate the backend first

The agent runs the AI CLI non-interactively, so **you must sign in once before
running the agent**. Each tool caches the credentials in your user environment
and reuses them on later runs, so this is a one-time step per machine (until you
log out or the session expires). Log in with the tool you selected:

| Backend        | Log in            | Check status           | Log out            |
| -------------- | ----------------- | ---------------------- | ------------------ |
| `kiro-cli`     | `kiro-cli login`  | `kiro-cli whoami`      | `kiro-cli logout`  |
| `codex`        | `codex login`     | `codex login status`   | `codex logout`     |
| `cursor-agent` | `cursor-agent login` | `cursor-agent status` | `cursor-agent logout` |

For non-interactive or headless environments (CI, remote servers without a
browser), the usage-based tools also accept an API key from the environment
instead of a browser login:

- **codex** — sign in with an API key, or export `OPENAI_API_KEY`. For a remote
  host without a browser, use `codex login --device-auth`. Credentials are
  cached in `~/.codex/auth.json`.
- **cursor-agent** — export `CURSOR_API_KEY` (or pass `--api-key`). The browser
  login flow can be suppressed with `NO_OPEN_BROWSER=1`.

kiro-cli's `kiro-cli login` supports a device-code flow (`--use-device-flow`)
for the same purpose.

## PowerPoint export

Passing `--pptx` writes a slide deck to `output/fleet-summary.pptx` alongside
the Markdown memos and fleet report. The deck has:

- One slide per project. The top of each slide carries three visuals side by
  side — **project health**, **project direction**, and **top contributors**.
  Health and contributors are derived deterministically from the collected git
  log, issues, and pull requests (bot/automation accounts are excluded from the
  contributor ranking). The project-health visual also folds in three one-line
  governance signals: whether a public ADOPTERS list, a security policy, and an
  OWNERS file exist ("documented" vs "none"). They report presence rather than
  detail — ADOPTERS formats are not standardised, whether a security process
  follows best practices is a qualitative judgement, and OWNERS content is
  project-specific — so the memo carries the depth while the visual carries the
  binary fact. These do not warrant visuals of their own since many projects
  have none.
  Project direction is a single sentence taken from the
  memo: the memo prompt asks the AI CLI to end its "Direction" section with an
  explicit `**Direction summary:**` one-liner, which the slide uses verbatim
  (older memos without the marker fall back to a heuristic summary). Below the
  visuals, the slide shows a focused recap of the project state — the executive
  summary, the key risks, and the memo's closing `**Overall assessment:**`
  one-liner — rather than the full memo, so it does not repeat the top visuals.
- A final **overall summary** slide rolling every project up by how much
  management attention it needs.

```bash
.venv/bin/python -m health_checker_agent --config repos.toml --pptx
```

The export relies on [`python-pptx`](https://python-pptx.readthedocs.io), which
is listed in `requirements.txt` (and available as the `pptx` optional extra).
It is imported only when `--pptx` is used, so the rest of the agent runs without
it.

## Running the tests

New code must ship with tests, and the suite must pass before any commit (see
[AGENTS.md](AGENTS.md)).

```bash
# With pytest
.venv/bin/python -m pytest -q

# Or with the standard library test runner
.venv/bin/python -m unittest discover -s tests
```

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).

Copyright 2026, Jan Melén.
