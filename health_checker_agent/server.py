"""ASGI entry point for the Project Health Checker web UI.

Exposes a module-level ``app`` so the container (and local development) can run:

    uvicorn health_checker_agent.server:app --host 0.0.0.0 --port 8080

The config path is read from the environment so the same image works with
different mounts:

- ``HEALTH_CHECKER_CONFIG``  path to ``repos.toml`` (default: ``repos.toml``)

Credentials are never read from or written to disk: they live only in the
process environment (set in the browser on the Credentials page, or exported in
the shell before launch). They must be re-entered after a restart.

Running this module directly starts uvicorn on 0.0.0.0:8080.
"""

from __future__ import annotations

import os

from .webapp import DEFAULT_CONFIG_PATH, create_app

app = create_app(
    config_path=os.environ.get("HEALTH_CHECKER_CONFIG", DEFAULT_CONFIG_PATH),
)


def main() -> None:
    """Run the web UI with uvicorn (used by ``python -m health_checker_agent.server``)."""
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HEALTH_CHECKER_HOST", "0.0.0.0"),
        port=int(os.environ.get("HEALTH_CHECKER_PORT", "8080")),
    )


if __name__ == "__main__":
    main()
