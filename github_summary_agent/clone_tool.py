"""Tool: clone or update a repository clone into a working directory.

Uses the ``git`` command exclusively (per AGENTS.md). Clones are kept so that
subsequent runs only need to fetch new commits rather than clone from scratch.
"""

from __future__ import annotations

import os

from .commands import run_command

DEFAULT_GIT_HOST = "https://github.com"


def repo_slug(repo: str) -> str:
    """Turn ``owner/name`` into a filesystem-safe directory name."""
    return repo.replace("/", "__")


def clone_or_update(
    repo: str,
    work_dir: str,
    *,
    git_host: str = DEFAULT_GIT_HOST,
    timeout: float | None = 600,
) -> str:
    """Ensure a local clone of ``repo`` exists under ``work_dir`` and is current.

    If the clone does not yet exist it is cloned; otherwise its default remote
    is fetched and the checked-out branch is fast-forwarded.

    Args:
        repo: Repository in ``owner/name`` form.
        work_dir: Directory under which clones are stored.
        git_host: Base git host URL.
        timeout: Optional command timeout in seconds.

    Returns:
        The path to the local clone.
    """
    os.makedirs(work_dir, exist_ok=True)
    dest = os.path.join(work_dir, repo_slug(repo))
    url = f"{git_host}/{repo}.git"

    if os.path.isdir(os.path.join(dest, ".git")):
        # Existing clone: fetch and fast-forward the current branch.
        run_command(["git", "-C", dest, "fetch", "--quiet", "origin"], timeout=timeout)
        run_command(
            ["git", "-C", dest, "pull", "--quiet", "--ff-only"],
            timeout=timeout,
            check=False,
        )
    else:
        run_command(["git", "clone", "--quiet", url, dest], timeout=timeout)

    return dest


def latest_commit_hash(repo_path: str, *, timeout: float | None = 30) -> str:
    """Return the HEAD commit hash of ``repo_path`` (empty string if none)."""
    result = run_command(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        timeout=timeout,
        check=False,
    )
    return result.stdout.strip() if result.ok else ""
