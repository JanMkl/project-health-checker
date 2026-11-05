"""Command-line entry point for the GitHub summary agent.

Runs against a TOML config describing the repositories to analyse. Each repo is
cloned into the working directory, analysed into its own memo, and a fleet
roll-up report classifies repos by how much management attention they need.

Example:
    python -m github_summary_agent --config repos.toml

A single repo can be analysed without a config file:
    python -m github_summary_agent --repo metal3-io/metal3-dev-env --since "30 days ago"
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .agent import OUTPUT_DIR, run_fleet, run_repo
from .config import DEFAULT_WORK_DIR, Config, ConfigError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github_summary_agent",
        description=(
            "Summarise GitHub projects' git activity, issues, and pull requests "
            "into markdown management memos via kiro-cli, plus a fleet roll-up."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a TOML config listing repos and settings.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=(
            "Analyse a single repository in owner/name form (alternative to "
            "--config)."
        ),
    )
    parser.add_argument(
        "--since",
        default=None,
        help=(
            'Start of the git log period, e.g. "30 days ago" or 2026-10-01. '
            "Required with --repo; overrides the config value when given."
        ),
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Optional end of the git log period.",
    )
    parser.add_argument(
        "--work-dir",
        default=DEFAULT_WORK_DIR,
        help=(
            "Directory the tool clones repositories into "
            f"(default: {DEFAULT_WORK_DIR})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help=f"Directory to write memos and reports into (default: {OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run the analysis even if the inputs have not changed.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the agent from command-line arguments.

    The GitHub token is read from the ``GITHUB_AUTH_TOKEN`` environment
    variable; it is intentionally not a CLI flag so the secret never appears in
    shell history or process listings.

    Returns:
        Process exit code (0 on success, non-zero on usage/config errors).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.config and not args.repo:
        parser.error("one of --config or --repo is required")
    if args.config and args.repo:
        parser.error("use either --config or --repo, not both")

    if args.repo:
        if not args.since:
            parser.error("--since is required with --repo")
        config = Config(
            repos=[args.repo],
            since=args.since,
            until=args.until,
            work_dir=args.work_dir,
            output_dir=args.output_dir,
        )
    else:
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
        # CLI flags override config values when explicitly provided.
        config = Config(
            repos=config.repos,
            since=args.since or config.since,
            until=args.until if args.until is not None else config.until,
            work_dir=args.work_dir if args.work_dir != DEFAULT_WORK_DIR else config.work_dir,
            output_dir=args.output_dir if args.output_dir != OUTPUT_DIR else config.output_dir,
        )

    if len(config.repos) == 1 and args.repo:
        result = run_repo(
            config.repos[0],
            since=config.since,
            until=config.until,
            work_dir=config.work_dir,
            output_dir=config.output_dir,
            force=args.force,
        )
        status = "analysed" if result.analysed else "reused existing memo"
        print(f"{result.repo}: {result.assessment.category} ({status})")
        print(f"Memo written to: {result.memo_path}")
        return 0

    fleet = run_fleet(config, force=args.force)
    analysed = sum(1 for r in fleet.results if r.analysed)
    reused = len(fleet.results) - analysed
    print(f"Analysed {len(fleet.results)} repos ({analysed} re-run, {reused} reused).")
    print(f"Fleet report written to: {fleet.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
