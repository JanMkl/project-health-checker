# GitHub Summary Agent

An agent that analyses one or many GitHub projects' git activity, issues, and
pull requests, asks an AI coding CLI to write a per-project management memo (in
Markdown), and rolls everything up into a single fleet report grouping projects
by how much management attention they need. The memo CLI is pluggable —
`kiro-cli` (default), `codex`, or `cursor-agent` — selected with `--backend` or
the `backend` config key.

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
5. **Health classification** (`health.py`) — deterministically sorts the repo
   into `healthy`, `attention`, or `investigate` from the collected counts.
6. **Memo generation** (`memo.py`) — builds a prompt from the commits, issues,
   and pull requests and pipes it to the selected AI CLI backend
   (`backends.py`) for the Markdown memo.

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
.venv/bin/python -m github_summary_agent --config repos.toml
```

This clones each repo under `output/repos/`, writes one memo per repo
(`output/<owner>__<name>-memo.md`), and a roll-up at `output/fleet-report.md`.

### A single repository

```bash
.venv/bin/python -m github_summary_agent \
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
.venv/bin/python -m github_summary_agent --config repos.toml --backend cursor-agent
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
  contributor ranking). Project direction is a single sentence taken from the
  memo: the memo prompt asks the AI CLI to end its "Direction" section with an
  explicit `**Direction summary:**` one-liner, which the slide uses verbatim
  (older memos without the marker fall back to a heuristic summary). Below the
  visuals, the slide shows a focused recap of the project state — the executive
  summary, the key risks, and the memo's closing `**Overall assessment:**`
  one-liner — rather than the full memo, so it does not repeat the top visuals.
- A final **overall summary** slide rolling every project up by how much
  management attention it needs.

```bash
.venv/bin/python -m github_summary_agent --config repos.toml --pptx
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
