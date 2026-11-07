# GitHub Summary Agent

An agent that analyses one or many GitHub projects' git activity, issues, and
pull requests, asks `kiro-cli` to write a per-project management memo (in
Markdown), and rolls everything up into a single fleet report grouping projects
by how much management attention they need.

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
   and pull requests and pipes it to `kiro-cli` for the Markdown memo.

Across all repos, `run_fleet` writes `output/fleet-report.md` grouping projects
into: requires management attention, needs investigation / keep an eye on, and
healthy (no attention needed).

The issues and pull requests (open and closed) let the memo identify active
contributors and community members by cross-referencing commit authors with
issue and PR authors, since commit authorship alone understates who is active.
Shared GitHub API plumbing (auth, redirects, error handling) lives in
`github_api.py`.

### Skipping unchanged analyses

Re-running kiro-cli for every repo is expensive. After each analysis the agent
stores an input *fingerprint* (commit count and latest commit, plus open/closed
issue and PR counts and newest timestamps) next to the memo. On a later run, if
the fingerprint is unchanged the existing memo is reused and kiro-cli is not
called again. Use `--force` to re-analyse regardless.

All memos, reports, state files, and repository clones are written under the
`output/` directory, which is the only location the agent is permitted to write
to.

## Requirements

- Python 3.10+
- `git`, `curl`, and `kiro-cli` available on your `PATH`
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
| `--force`      | no                  | Re-run analysis even if the inputs have not changed.             |
| `--pptx`       | no                  | Also write a PowerPoint deck of the findings (see below).        |

## PowerPoint export

Passing `--pptx` writes a slide deck to `output/fleet-summary.pptx` alongside
the Markdown memos and fleet report. The deck has:

- One slide per project. The top of each slide carries three visuals side by
  side — **project health**, **project direction**, and **top contributors**.
  Health and contributors are derived deterministically from the collected git
  log, issues, and pull requests (bot/automation accounts are excluded from the
  contributor ranking). Project direction is a single sentence taken from the
  memo: the memo prompt asks kiro-cli to end its "Direction" section with an
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
