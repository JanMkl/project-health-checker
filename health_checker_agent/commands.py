"""Shell command execution constrained by the AGENTS.md access policy.

Only the commands listed in ``ALLOWED_COMMANDS`` may be executed. Every tool in
this package routes its shell access through :func:`run_command` so the policy
is enforced in a single place.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Sequence

from .backends import BACKEND_COMMANDS

# Shell commands permitted by AGENTS.md. The AI-CLI backends (kiro-cli, codex,
# cursor-agent) are contributed by ``backends.BACKEND_COMMANDS`` so the memo
# tool and the allow-list cannot drift apart.
ALLOWED_COMMANDS = frozenset({"git", "curl"}) | BACKEND_COMMANDS


class CommandNotAllowedError(Exception):
    """Raised when a command outside the allow-list is attempted."""


@dataclass(frozen=True)
class CommandResult:
    """Result of a completed shell command."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_command(
    args: Sequence[str],
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    check: bool = True,
    stdin_input: str | None = None,
) -> CommandResult:
    """Run an allow-listed shell command and capture its output.

    Args:
        args: The command and its arguments. ``args[0]`` must be in
            ``ALLOWED_COMMANDS``.
        cwd: Working directory for the command.
        timeout: Optional timeout in seconds.
        check: When True, raise ``subprocess.CalledProcessError`` on non-zero
            exit.
        stdin_input: Optional text fed to the command's standard input. Use this
            for large payloads that would exceed the OS argument-length limit if
            passed as a command-line argument.

    Raises:
        CommandNotAllowedError: If the command is not allow-listed.
        ValueError: If ``args`` is empty.
    """
    if not args:
        raise ValueError("args must not be empty")

    program = args[0]
    if program not in ALLOWED_COMMANDS:
        raise CommandNotAllowedError(
            f"Command {program!r} is not allowed. "
            f"Allowed commands: {sorted(ALLOWED_COMMANDS)}"
        )

    completed = subprocess.run(
        list(args),
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
        input=stdin_input,
    )

    result = CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )

    if check and not result.ok:
        raise subprocess.CalledProcessError(
            result.returncode, list(args), result.stdout, result.stderr
        )

    return result
