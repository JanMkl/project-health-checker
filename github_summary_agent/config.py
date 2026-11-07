"""Configuration for multi-repository runs.

Uses TOML (parsed with the standard-library :mod:`tomllib`) as a more Pythonic
replacement for the shell-oriented ``repos.conf``. Example:

.. code-block:: toml

    # repos.toml
    since = "90 days ago"
    until = "2026-11-01"        # optional
    work_dir = "output/repos"   # where clones are kept (optional)
    output_dir = "output"       # where reports are written (optional)
    backend = "kiro-cli"        # AI CLI: kiro-cli | codex | cursor-agent (optional)
    repos = [
        "metal3-io/metal3-dev-env",
        "metal3-io/baremetal-operator",
    ]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import List

from .backends import DEFAULT_BACKEND, SUPPORTED_BACKENDS

# Defaults chosen to stay within the AGENTS.md write policy (everything under
# ``output/``).
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_WORK_DIR = "output/repos"


class ConfigError(Exception):
    """Raised when a config file is missing required fields or malformed."""


@dataclass(frozen=True)
class Config:
    """Parsed multi-repository configuration."""

    repos: List[str]
    since: str
    until: str | None = None
    work_dir: str = DEFAULT_WORK_DIR
    output_dir: str = DEFAULT_OUTPUT_DIR
    backend: str = DEFAULT_BACKEND


def _validate_repo(repo: object) -> str:
    if not isinstance(repo, str) or repo.count("/") != 1 or not all(repo.split("/")):
        raise ConfigError(
            f"Invalid repo entry {repo!r}; expected 'owner/name' form."
        )
    return repo


def parse_config(raw: str) -> Config:
    """Parse TOML config text into a :class:`Config`.

    Raises:
        ConfigError: If required fields are missing or values are the wrong
            type.
    """
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse config as TOML: {exc}") from exc

    repos = data.get("repos")
    if not isinstance(repos, list) or not repos:
        raise ConfigError("Config must define a non-empty 'repos' list.")
    repos = [_validate_repo(r) for r in repos]

    since = data.get("since")
    if not isinstance(since, str) or not since:
        raise ConfigError("Config must define a non-empty 'since' string.")

    until = data.get("until")
    if until is not None and not isinstance(until, str):
        raise ConfigError("'until' must be a string if provided.")

    work_dir = data.get("work_dir", DEFAULT_WORK_DIR)
    output_dir = data.get("output_dir", DEFAULT_OUTPUT_DIR)
    if not isinstance(work_dir, str) or not isinstance(output_dir, str):
        raise ConfigError("'work_dir' and 'output_dir' must be strings.")

    backend = data.get("backend", DEFAULT_BACKEND)
    if not isinstance(backend, str) or backend not in SUPPORTED_BACKENDS:
        raise ConfigError(
            f"'backend' must be one of {', '.join(SUPPORTED_BACKENDS)}."
        )

    return Config(
        repos=repos,
        since=since,
        until=until,
        work_dir=work_dir,
        output_dir=output_dir,
        backend=backend,
    )


def load_config(path: str) -> Config:
    """Load and parse a TOML config file from ``path``."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read().decode("utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    return parse_config(raw)
