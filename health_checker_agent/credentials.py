"""Persisted credentials for the web UI.

The agent itself reads secrets from the process environment (the GitHub token
from ``GITHUB_AUTH_TOKEN``; the AI CLIs from their own env vars / login caches).
The web UI lets a user enter those secrets in the browser, so we need somewhere
to keep them between requests and across container restarts.

This module stores them in a single ``credentials.env`` file (``KEY=value`` per
line, ``0600`` permissions) under a configurable directory, and applies them to
``os.environ`` so the next analysis run — in this same process — picks them up
immediately. In the container the directory is a mounted volume, so credentials
survive restarts.

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

_FILENAME = "credentials.env"


class CredentialStore:
    """Load, persist, and apply credentials from a directory."""

    def __init__(self, directory: str):
        self.directory = directory
        self.path = os.path.join(directory, _FILENAME)

    def load(self) -> Dict[str, str]:
        """Return the stored credentials as a ``{key: value}`` mapping."""
        creds: Dict[str, str] = {}
        if not os.path.exists(self.path):
            return creds
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                env_name, _, value = line.partition("=")
                for key, mapped in CREDENTIAL_ENV_VARS.items():
                    if mapped == env_name.strip():
                        creds[key] = value.strip()
        return creds

    def status(self) -> Dict[str, bool]:
        """Return which credentials are set, without exposing their values."""
        stored = self.load()
        env = os.environ
        return {
            key: bool(stored.get(key) or env.get(env_name))
            for key, env_name in CREDENTIAL_ENV_VARS.items()
        }

    def save(self, updates: Dict[str, str]) -> None:
        """Merge ``updates`` into the store and persist them.

        Keys mapping to an empty string are removed. Unknown keys are ignored.
        The file is written with ``0600`` permissions.
        """
        current = self.load()
        for key, value in updates.items():
            if key not in CREDENTIAL_ENV_VARS:
                continue
            value = (value or "").strip()
            if value:
                current[key] = value
            else:
                current.pop(key, None)

        os.makedirs(self.directory, exist_ok=True)
        lines = [
            f"{CREDENTIAL_ENV_VARS[key]}={value}" for key, value in current.items()
        ]
        # Write atomically-ish with restrictive permissions.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + ("\n" if lines else ""))

        self.apply()

    def apply(self) -> None:
        """Export stored credentials into ``os.environ`` for this process."""
        for key, value in self.load().items():
            if value:
                os.environ[CREDENTIAL_ENV_VARS[key]] = value
