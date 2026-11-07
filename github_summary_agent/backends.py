"""Pluggable AI-CLI backends for generating the memo.

The agent asks an AI coding CLI to turn the collected project activity into a
Markdown memo. Historically this was hard-coded to ``kiro-cli``; this module
abstracts the invocation so end users can pick whichever assistant CLI they
have installed:

- ``kiro-cli`` (default)
- ``codex`` (OpenAI Codex CLI, via its non-interactive ``exec`` subcommand)
- ``cursor-agent`` (Cursor's agent CLI, via its non-interactive print mode)

Each backend knows how to build an argument vector for a one-shot,
non-interactive run that reads a prompt and prints the result to stdout. The
prompt is always fed on stdin to stay clear of the OS argument-length limit
(ARG_MAX) for large repositories.

To keep the AGENTS.md command allow-list enforced in one place, the executable
each backend uses is also registered in :data:`commands.ALLOWED_COMMANDS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

# Backend identifiers accepted on the CLI / in config.
KIRO = "kiro-cli"
CODEX = "codex"
CURSOR = "cursor-agent"

DEFAULT_BACKEND = KIRO


class UnknownBackendError(ValueError):
    """Raised when an unrecognised backend name is requested."""


@dataclass(frozen=True)
class Backend:
    """How to invoke a particular AI CLI for a one-shot memo generation.

    Attributes:
        name: The backend identifier (also the executable name).
        build_args: Builds the argv for a non-interactive run. The prompt is
            supplied separately on stdin, so most backends ignore it, but it is
            passed in for backends that need it on the command line.
    """

    name: str
    build_args: Callable[[], List[str]]


def _kiro_args() -> List[str]:
    # `kiro-cli chat` reads the prompt from stdin when no positional INPUT is
    # given. `--no-interactive` runs without expecting further input and
    # `--trust-all-tools` avoids blocking on tool-permission prompts.
    return ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools"]


def _codex_args() -> List[str]:
    # `codex exec` is the Codex CLI's non-interactive mode; it reads the prompt
    # from stdin when no prompt argument is given and prints the final message
    # to stdout.
    return ["codex", "exec", "-"]


def _cursor_args() -> List[str]:
    # `cursor-agent -p/--print` runs non-interactively and prints the result;
    # `--output-format text` keeps stdout to plain text (no JSON envelope). The
    # prompt is read from stdin.
    return ["cursor-agent", "--print", "--output-format", "text"]


# Registry of the supported backends.
_BACKENDS: Dict[str, Backend] = {
    KIRO: Backend(KIRO, _kiro_args),
    CODEX: Backend(CODEX, _codex_args),
    CURSOR: Backend(CURSOR, _cursor_args),
}

# Executable names the backends may launch, for the command allow-list.
BACKEND_COMMANDS = frozenset(b.name for b in _BACKENDS.values())

# Names accepted from users, for help text and validation.
SUPPORTED_BACKENDS = tuple(_BACKENDS.keys())


def get_backend(name: str) -> Backend:
    """Return the :class:`Backend` for ``name``.

    Raises:
        UnknownBackendError: If ``name`` is not a supported backend.
    """
    try:
        return _BACKENDS[name]
    except KeyError:
        raise UnknownBackendError(
            f"Unknown backend {name!r}. Supported backends: "
            f"{', '.join(SUPPORTED_BACKENDS)}."
        ) from None
