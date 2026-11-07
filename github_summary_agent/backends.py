"""Pluggable AI-CLI backends for generating the memo.

The agent asks an AI coding CLI to turn the collected project activity into a
Markdown memo. Historically this was hard-coded to ``kiro-cli``; this module
abstracts the invocation so end users can pick whichever assistant CLI they
have installed:

- ``kiro-cli`` (default)
- ``codex`` (OpenAI Codex CLI, via its non-interactive ``exec`` subcommand)
- ``cursor-agent`` (Cursor's agent CLI, via its non-interactive print mode)

Each backend runs the tool once, non-interactively, feeding the prompt on stdin
(to stay clear of the OS argument-length limit, ARG_MAX, for large repos) and
returning just the generated memo text.

The backends differ in how they emit their result:

- ``kiro-cli`` and ``cursor-agent`` print the final text to stdout, so we read
  it directly.
- ``codex exec`` prints a framed event log to stdout (header, prompt echo,
  token usage, ...), so we ask it to write only the final message to a file via
  ``--output-last-message`` and read that back.

To keep the AGENTS.md command allow-list enforced in one place, the executable
each backend uses is also registered in :data:`commands.ALLOWED_COMMANDS`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

# Backend identifiers accepted on the CLI / in config.
KIRO = "kiro-cli"
CODEX = "codex"
CURSOR = "cursor-agent"

DEFAULT_BACKEND = KIRO


class UnknownBackendError(ValueError):
    """Raised when an unrecognised backend name is requested."""


# A runner executes the backend and returns the memo text. It receives the
# backend's resolved argv, the prompt, the low-level command executor (injected
# to avoid an import cycle with :mod:`commands`), and an optional timeout.
RunFn = Callable[[List[str], str, Callable, "float | None"], str]


@dataclass(frozen=True)
class Backend:
    """How to invoke a particular AI CLI for a one-shot memo generation.

    Attributes:
        name: The backend identifier.
        argv: The base command and arguments for a non-interactive run. The
            first element is the default executable name.
        run: Strategy that executes the tool and returns the memo text.
        executables: Candidate executable names, in preference order. The first
            one found on ``PATH`` is used; this lets a tool that installs under
            more than one name (e.g. Cursor ships both ``cursor-agent`` and
            ``agent``) work regardless of which entry point exists. Defaults to
            just ``argv[0]``.
    """

    name: str
    argv: List[str]
    run: RunFn
    executables: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.executables:
            object.__setattr__(self, "executables", (self.argv[0],))

    def _resolve_argv(self) -> List[str]:
        """Return argv with argv[0] set to the first executable found on PATH.

        Falls back to the first candidate name when none is found, so the error
        surfaced to the user names the primary executable.
        """
        chosen = next((e for e in self.executables if shutil.which(e)), None)
        exe = chosen or self.executables[0]
        return [exe, *self.argv[1:]]

    def generate(self, prompt: str, runner: Callable, timeout: float | None) -> str:
        """Run the backend for ``prompt`` and return the memo text."""
        return self.run(self._resolve_argv(), prompt, runner, timeout)


def _run_stdout(argv: List[str], prompt: str, runner: Callable, timeout) -> str:
    """Run a backend that prints the clean result to stdout."""
    result = runner(argv, timeout=timeout, stdin_input=prompt)
    return result.stdout.strip()


def _run_codex(argv: List[str], prompt: str, runner: Callable, timeout) -> str:
    """Run codex, capturing only the final message via --output-last-message.

    ``codex exec`` writes a framed event log to stdout, so reading stdout would
    pollute the memo. ``--output-last-message`` writes just the final agent
    message to a file, which is exactly the memo we want.
    """
    fd, last_message_path = tempfile.mkstemp(prefix="codex-memo-", suffix=".md")
    os.close(fd)
    try:
        runner(
            argv + ["--output-last-message", last_message_path],
            timeout=timeout,
            stdin_input=prompt,
        )
        with open(last_message_path, encoding="utf-8") as fh:
            return fh.read().strip()
    finally:
        try:
            os.remove(last_message_path)
        except OSError:
            pass


# Base argv per backend.
#
# - `kiro-cli chat` reads the prompt from stdin when no positional INPUT is
#   given. `--no-interactive` runs without further input; `--trust-all-tools`
#   avoids blocking on tool-permission prompts.
# - `codex exec -` reads the prompt from stdin (verified against codex-cli
#   0.167.0: "If not provided as an argument (or if `-` is used), instructions
#   are read from stdin").
# - `cursor-agent --print` runs non-interactively; `--output-format text` keeps
#   stdout to plain text. The prompt is read from stdin. Cursor installs the
#   tool under two names (`cursor-agent` and the bare `agent`), so both are
#   accepted; whichever is on PATH is used.
_BACKENDS: Dict[str, Backend] = {
    KIRO: Backend(
        KIRO, ["kiro-cli", "chat", "--no-interactive", "--trust-all-tools"], _run_stdout
    ),
    CODEX: Backend(CODEX, ["codex", "exec", "-"], _run_codex),
    CURSOR: Backend(
        CURSOR,
        ["cursor-agent", "--print", "--output-format", "text"],
        _run_stdout,
        executables=("cursor-agent", "agent"),
    ),
}

# Executable names the backends may launch, for the command allow-list. Includes
# every candidate executable so an alternately-named entry point (e.g. Cursor's
# bare `agent`) is still permitted.
BACKEND_COMMANDS = frozenset(
    exe for b in _BACKENDS.values() for exe in b.executables
)

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
