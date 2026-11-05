"""Command-line entry point for the GitHub summary agent.

Example:
    python -m github_summary_agent \\
        --repo metal3-io/metal3-dev-env \\
        --repo-path /tmp/metal3-dev-env \\
        --since "30 days ago"
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .agent import OUTPUT_DIR, summarise_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github_summary_agent",
        description=(
            "Summarise a GitHub project's git activity and open issues into a "
            "markdown management memo via kiro-cli."
        ),
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/name form, e.g. metal3-io/metal3-dev-env",
    )
    parser.add_argument(
        "--repo-path",
        required=True,
        help="Path to a local clone of the repository (used for git logs).",
    )
    parser.add_argument(
        "--since",
        required=True,
        help='Start of the git log period, e.g. "30 days ago" or 2026-10-01.',
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Optional end of the git log period.",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help=f"Directory to write the memo into (default: {OUTPUT_DIR}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the agent from command-line arguments.

    The GitHub token is read from the ``GITHUB_AUTH_TOKEN`` environment
    variable inside the issues tool; it is intentionally not a CLI flag so the
    secret never appears in shell history or process listings.

    Returns:
        Process exit code (0 on success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    result = summarise_project(
        repo=args.repo,
        repo_path=args.repo_path,
        since=args.since,
        until=args.until,
        output_dir=args.output_dir,
    )

    print(f"Memo written to: {result.memo_path}")
    print(f"Commits analysed: {result.git_log.count}")
    print(f"Open issues analysed: {result.issues.count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
