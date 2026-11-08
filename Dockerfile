# Project Health Checker — container image.
#
# Bundles the Python agent, the FastAPI web UI, and the AI coding CLIs the agent
# can drive (codex, cursor-agent, and optionally kiro-cli). The web UI listens
# on port 8080.
#
# Build:   docker build -t health-checker-agent .
# Run:     docker compose up   (see docker-compose.yml)

FROM python:3.12-slim

# --- base tooling -----------------------------------------------------------
# git + curl are required by the agent itself (see AGENTS.md). nodejs/npm are
# needed to install the codex CLI. unzip is required by the kiro-cli installer.
# ca-certificates for TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        unzip \
        ca-certificates \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# --- AI CLI backends --------------------------------------------------------
# codex: official npm package (provides the `codex` binary).
RUN npm install -g @openai/codex \
    && codex --version

# cursor-agent: official install script. Installs `cursor-agent` (and `agent`)
# under /root/.local/bin, which we add to PATH below.
RUN curl -fsSL https://cursor.com/install | bash
ENV PATH="/root/.local/bin:${PATH}"

# kiro-cli: official installer. Installs `kiro-cli` under /root/.local/bin
# (already on PATH above). `--no-modify-path` skips the installer's shell-rc
# edits, which are pointless in an image. The binary is large (~400 MB), so this
# layer dominates the image size; set INSTALL_KIRO_CLI=false to skip it when you
# only use the codex or cursor-agent backends.
ARG INSTALL_KIRO_CLI=true
RUN if [ "$INSTALL_KIRO_CLI" = "true" ]; then \
        curl -fsSL https://cli.kiro.dev/install | bash -s -- --no-modify-path --force \
        && kiro-cli --version; \
    else \
        echo "Skipping kiro-cli install (INSTALL_KIRO_CLI=$INSTALL_KIRO_CLI); codex and cursor-agent backends remain available"; \
    fi

# --- Python application -----------------------------------------------------
WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY pyproject.toml ./
COPY health_checker_agent ./health_checker_agent
# Seed a default config if the mounted volume doesn't provide one.
COPY repos.toml.example ./repos.toml.example

# Directory the app writes generated memos/clones into (mounted as a volume by
# docker-compose so output survives restarts). Credentials are never written to
# disk — they live only in the running process's environment.
RUN mkdir -p /app/output

# The web UI configuration (paths read by server.py).
ENV HEALTH_CHECKER_CONFIG=/app/repos.toml \
    HEALTH_CHECKER_HOST=0.0.0.0 \
    HEALTH_CHECKER_PORT=8080

EXPOSE 8080

# Seed repos.toml from the example on first start if it is missing, then launch
# the web UI.
CMD ["sh", "-c", "[ -f /app/repos.toml ] || cp /app/repos.toml.example /app/repos.toml; exec python -m health_checker_agent.server"]
