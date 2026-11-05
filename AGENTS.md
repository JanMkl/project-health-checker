# GitHub Summary Agent

An agent that fetches git logs from GitHub projects and produces summaries.

## Agent Access Policy

This file defines the access boundaries for the agent. The agent must operate strictly within these limits.

### Allowed Shell Commands

The agent may only invoke the following shell commands:

- `kiro-cli`
- `git`
- `curl`

Any other shell command is disallowed.

### Filesystem Access

- **Write access:** The agent may only write to the `output/` directory.
- All generated summaries, logs, and artifacts must be placed under `output/`.
- The agent must not modify files outside of `output/`.

### Network Access

- The agent may connect to `http://github.com` only.
- Allowed methods of access:
  - `git` (e.g. clone/fetch to read git logs)
  - `curl` (e.g. fetch data over HTTP)
- No other network destinations are permitted.

### Allowed Projects

- The list of repositories the agent is permitted to access will be defined here later.
- Until a project is explicitly listed, the agent has no project access.

<!-- Add allowed project repositories below -->

## Development Rules

### Testing Requirement

- Before any new commit is made to this repository, the test suite **must** be passing.
- Any new code added to this repository **must** be accompanied by tests.
- Do not commit code that lacks test coverage or that causes existing tests to fail.
