"""ASGI entry point for the Project Health Checker web UI.

Exposes a module-level ``app`` so the container (and local development) can run:

    uvicorn health_checker_agent.server:app --host 0.0.0.0 --port 8080

Paths are read from the environment so the same image works with different
mounts:

- ``HEALTH_CHECKER_CONFIG``       path to ``repos.toml`` (default: ``repos.toml``)
- ``HEALTH_CHECKER_SECRETS_DIR``  directory for persisted credentials
                                  (default: ``secrets``)

Running this module directly starts uvicorn on 0.0.0.0:8080.
"""

from __future__ import annotations

import os

from .webapp import DEFAULT_CONFIG_PATH, DEFAULT_CREDENTIALS_DIR, create_app

app = create_app(
    config_path=os.environ.get("HEALTH_CHECKER_CONFIG", DEFAULT_CONFIG_PATH),
    credentials_dir=os.environ.get(
        "HEALTH_CHECKER_SECRETS_DIR", DEFAULT_CREDENTIALS_DIR
    ),
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
