# GitHub Summary Agent

An agent that fetches a GitHub project's git activity and open issues, then asks
`kiro-cli` to write a management memo (in Markdown) analysing the project's
**direction**, **major contributors**, and **health**.

The access policy for the agent is defined in [AGENTS.md](AGENTS.md).

## How it works

The pipeline has three tools, orchestrated by `summarise_project`:

1. **Git log tool** (`git_log_tool.py`) — runs `git log` over a time window on a
   local clone of the project and collects commits (author, date, subject).
2. **Open issues tool** (`issues_tool.py`) — uses `curl` against the GitHub REST
   API to fetch open issues (used for the project-direction analysis).
3. **Memo generation** (`memo.py`) — builds a prompt from the log and issues and
   pipes it to `kiro-cli`, which returns the Markdown memo.

The memo is written to the `output/` directory, which is the only location the
agent is permitted to write to.

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

The git log tool reads a **local clone**, so first clone the target project,
then point the agent at it.

```bash
# 1. Clone the target project
git clone https://github.com/metal3-io/metal3-dev-env.git /tmp/metal3-dev-env

# 2. Run the agent for the last 30 days
.venv/bin/python -m github_summary_agent \
    --repo metal3-io/metal3-dev-env \
    --repo-path /tmp/metal3-dev-env \
    --since "30 days ago"
```

This writes `output/metal3-io__metal3-dev-env-memo.md`.

### More examples

Summarise a fixed date range:

```bash
.venv/bin/python -m github_summary_agent \
    --repo metal3-io/metal3-dev-env \
    --repo-path /tmp/metal3-dev-env \
    --since 2026-10-01 \
    --until 2026-10-31
```

Write the memo to a custom directory:

```bash
.venv/bin/python -m github_summary_agent \
    --repo metal3-io/metal3-dev-env \
    --repo-path /tmp/metal3-dev-env \
    --since "2 weeks ago" \
    --output-dir output
```

### Options

| Flag           | Required | Description                                               |
| -------------- | -------- | --------------------------------------------------------- |
| `--repo`       | yes      | Repository in `owner/name` form.                          |
| `--repo-path`  | yes      | Path to a local clone of the repository (for git logs).   |
| `--since`      | yes      | Start of the period, e.g. `"30 days ago"` or `2026-10-01`.|
| `--until`      | no       | Optional end of the period.                               |
| `--output-dir` | no       | Directory to write the memo into (default: `output`).     |

## Running the tests

New code must ship with tests, and the suite must pass before any commit (see
[AGENTS.md](AGENTS.md)).

```bash
# With pytest
.venv/bin/python -m pytest -q

# Or with the standard library test runner
.venv/bin/python -m unittest discover -s tests
```
