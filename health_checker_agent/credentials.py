"""In-memory credentials for the web UI.

For safety, secrets are **never written to disk**. The process environment is
the single source of truth: the agent already reads the GitHub token from
``GITHUB_AUTH_TOKEN`` and the AI CLIs from their own env vars, so the web UI
simply sets those variables in ``os.environ`` for the running process.

Consequences of this design:

- Credentials entered in the browser live only in the running process's memory.
  When the process (or container) stops, they are gone and must be re-entered.
- Credentials exported in the shell before launch (e.g. ``export
  GITHUB_AUTH_TOKEN=...``) are picked up automatically, so a non-container run
  behaves as before.
- ``kiro-cli`` is not covered here: it uses an interactive device-code login
  (run ``kiro-cli login`` inside the container), not an environment variable.

Only a fixed allow-list of keys is accepted, and values are never echoed back to
the browser (the UI shows whether a key is set, not its value).
"""

from __future__ import annotations

import os
from typing import Dict

# The secrets the UI manages, mapped to the environment variable each one sets.
#   github_token  -> GITHUB_AUTH_TOKEN  (GitHub REST API auth)
#   openai_api_key-> OPENAI_API_KEY     (codex backend)
#   cursor_api_key-> CURSOR_API_KEY     (cursor-agent backend)
CREDENTIAL_ENV_VARS: Dict[str, str] = {
    "github_token": "GITHUB_AUTH_TOKEN",
    "openai_api_key": "OPENAI_API_KEY",
    "cursor_api_key": "CURSOR_API_KEY",
}


class CredentialStore:
    """Hold credentials in the process environment only (never on disk)."""

    def status(self) -> Dict[str, bool]:
        """Return which credentials are set, without exposing their values."""
        return {
            key: bool(os.environ.get(env_name))
            for key, env_name in CREDENTIAL_ENV_VARS.items()
        }

    def save(self, updates: Dict[str, str]) -> None:
        """Apply non-empty ``updates`` to the process environment.

        A non-empty value sets the corresponding environment variable. An empty
        (or whitespace-only) value is ignored so the UI's "leave blank to keep"
        behaviour holds — a field the user did not fill in does not wipe an
        existing value. Use :meth:`clear` to remove a credential. Unknown keys
        are ignored. Nothing is written to disk.
        """
        for key, value in updates.items():
            if key not in CREDENTIAL_ENV_VARS:
                continue
            value = (value or "").strip()
            if value:
                os.environ[CREDENTIAL_ENV_VARS[key]] = value

    def clear(self, keys) -> None:
        """Remove the environment variables for the given credential ``keys``."""
        for key in keys:
            env_name = CREDENTIAL_ENV_VARS.get(key)
            if env_name:
                os.environ.pop(env_name, None)

    def apply(self) -> None:
        """No-op: the environment is already the source of truth.

        Kept for API compatibility with callers that applied a disk-backed store
        to the environment on startup / before a run.
        """
        return None
