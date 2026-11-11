"""Shared helpers for talking to the GitHub REST API via curl.

Centralises the curl invocation (auth token, redirect following, error
handling) so the issues and pull-request tools stay consistent. Uses ``curl``
exclusively, per AGENTS.md.

Note: GitHub serves its REST API from ``api.github.com``. AGENTS.md lists
``github.com`` as the allowed host; the API host is a subdomain of it. The base
URL is configurable so the policy host can be adjusted centrally.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
from typing import Any, List

from .commands import run_command

DEFAULT_API_BASE = "https://api.github.com"

# Environment variable holding an optional GitHub token. When present, it is
# sent as a Bearer token to raise the API rate limit (5000/hour vs 60/hour).
TOKEN_ENV_VAR = "GITHUB_AUTH_TOKEN"


class GitHubApiError(Exception):
    """Raised when the GitHub API returns an error instead of list data."""


def resolve_token(token: str | None) -> str | None:
    """Return the explicit token, or fall back to the environment variable."""
    return token if token is not None else os.environ.get(TOKEN_ENV_VAR)


def _curl_args(url: str, token: str | None, *, fail: bool = True) -> List[str]:
    """Build the curl argv for a GitHub API GET.

    Args:
        url: Fully-qualified API URL to request.
        token: Optional GitHub token (sent as a Bearer header when present).
        fail: When True, add ``--fail`` so HTTP errors become a non-zero exit.
            Callers that need to distinguish 404 from other outcomes pass False.
    """
    args = [
        "curl",
        "--silent",
        "--show-error",
    ]
    if fail:
        args.append("--fail")
    # Follow redirects (e.g. HTTP 301 when a repository has been renamed).
    args += ["--location", "--header", "Accept: application/vnd.github+json"]

    effective_token = resolve_token(token)
    if effective_token:
        args += ["--header", f"Authorization: Bearer {effective_token}"]

    args.append(url)
    return args


def fetch_list(
    url: str,
    *,
    repo: str,
    token: str | None = None,
    timeout: float | None = 60,
) -> List[dict]:
    """GET ``url`` with curl and return a parsed JSON list.

    Args:
        url: Fully-qualified API URL to request.
        repo: Repository in ``owner/name`` form, for error messages.
        token: Optional GitHub token. When ``None``, the ``GITHUB_AUTH_TOKEN``
            environment variable is used if set.
        timeout: Optional command timeout in seconds.

    Returns:
        The parsed JSON array as a list of dicts.

    Raises:
        GitHubApiError: If the API returns an error object (a JSON object with
            a ``message``) or any non-list payload.
    """
    args = _curl_args(url, token)

    try:
        result = run_command(args, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        # The command's argv carries the "Authorization: Bearer <token>" header;
        # letting the raw CalledProcessError propagate would leak the token into
        # error messages and reports. Raise a clean, token-free error instead.
        raise GitHubApiError(
            f"GitHub API request for {repo} failed "
            f"(curl exit {exc.returncode})"
        ) from None
    return _parse_list(result.stdout, repo=repo)


def fetch_text(
    url: str,
    *,
    token: str | None = None,
    timeout: float | None = 60,
) -> str | None:
    """Fetch a single file's text via the GitHub contents API.

    The contents endpoint
    (``.../repos/<owner>/<repo>/contents/<path>``) returns a JSON object whose
    ``content`` is base64-encoded. This decodes and returns it.

    Returns ``None`` when the file does not exist (HTTP 404) or the response is
    not a decodable file object, so callers can treat "no such file" as a normal
    outcome rather than an error. Never raises on a missing file, and never
    leaks the token in an exception.
    """
    # ``--fail`` is omitted so a 404 yields a JSON error body we can detect,
    # rather than a non-zero exit we would have to interpret.
    args = _curl_args(url, token, fail=False)
    try:
        result = run_command(args, timeout=timeout, check=False)
    except (subprocess.SubprocessError, OSError):
        return None

    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    # Error payloads (404, rate limit, ...) are JSON objects without "content".
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return None
    content = data.get("content")
    if not isinstance(content, str):
        return None
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError):
        return None


def _parse_list(raw: str, repo: str) -> List[dict]:
    data: Any = json.loads(raw) if raw.strip() else []

    # A successful list response is a JSON array. The API returns a JSON object
    # instead when something goes wrong (e.g. issues disabled, repo not found,
    # rate limited), e.g. {"message": "...", "documentation_url": "..."}.
    if isinstance(data, dict):
        message = data.get("message", "unexpected response from GitHub API")
        raise GitHubApiError(f"GitHub API error for {repo}: {message}")
    if not isinstance(data, list):
        raise GitHubApiError(
            f"GitHub API error for {repo}: expected a list, "
            f"got {type(data).__name__}"
        )

    # Keep only well-formed objects; defensively drop anything else.
    return [item for item in data if isinstance(item, dict)]
