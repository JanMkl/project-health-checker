# GitHub Summary Agent

An agent that fetches git logs from GitHub projects and produces summaries.

## Agent Access Policy

This file defines the access boundaries for the agent. The agent must operate strictly within these limits.

### Allowed Shell Commands

The agent may only invoke the following shell commands:

- One AI coding CLI used to write the memos, selected by configuration:
  `kiro-cli` (default), `codex`, or `cursor-agent` (which Cursor also installs
  under the bare name `agent`).
- `git`
- `curl`

Any other shell command is disallowed.

### Filesystem Access

- **Write access:** The agent may only write to the `output/` directory.
- All generated summaries, memos, reports, state files, and artifacts must be
  placed under `output/`.
- Repository clones created for analysis must also live under `output/`. The
  default working directory is `output/repos/`. If a working directory outside
  `output/` is configured, that is outside this policy and must be approved
  explicitly.
- The agent must not modify files outside of `output/`.

### Network Access

- The agent may connect to `http://github.com` only.
- Allowed methods of access:
  - `git` (e.g. clone/fetch to read git logs)
  - `curl` (e.g. fetch data over HTTP)
- No other network destinations are permitted.

### Allowed Projects

- The set of repositories the agent may access is defined by the `repos`
  list in [`repos.toml`](repos.toml) (or the `--repo` argument for a
  single-repository run). That configuration is the single source of truth for
  allowed projects.
- The agent may only clone, fetch, or query repositories that appear in that
  configuration. Any repository not listed there is out of scope and must not
  be accessed.
- Each entry must be a public GitHub repository in `owner/name` form; the agent
  reads git history and the public issues/pull-requests API only.
- To grant or revoke access to a project, edit `repos.toml`; do not hard-code a
  separate allow-list here that could drift from the configuration.

## Development Rules

### Testing Requirement

- Before any new commit is made to this repository, the test suite **must** be passing.
- Any new code added to this repository **must** be accompanied by tests.
- Do not commit code that lacks test coverage or that causes existing tests to fail.
