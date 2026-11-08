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
# needed to install the codex CLI. ca-certificates for TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
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

# kiro-cli: there is no publicly scriptable installer URL we can pin here, and
# the binary is large (~400 MB). Provide its install as an optional build
# argument so operators who use the kiro-cli backend can supply the command for
# their platform, e.g.:
#   docker build --build-arg KIRO_CLI_INSTALL="curl -fsSL <url> | bash" .
# Left empty by default; the codex and cursor-agent backends work without it.
ARG KIRO_CLI_INSTALL=""
RUN if [ -n "$KIRO_CLI_INSTALL" ]; then \
        sh -c "$KIRO_CLI_INSTALL" && kiro-cli --version; \
    else \
        echo "kiro-cli not installed (KIRO_CLI_INSTALL not set); codex and cursor-agent backends are available"; \
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

# Directories the app reads/writes. Mounted as volumes by docker-compose so
# generated memos, clones, and credentials survive restarts.
RUN mkdir -p /app/output /app/secrets

# The web UI configuration (paths read by server.py).
ENV HEALTH_CHECKER_CONFIG=/app/repos.toml \
    HEALTH_CHECKER_SECRETS_DIR=/app/secrets \
    HEALTH_CHECKER_HOST=0.0.0.0 \
    HEALTH_CHECKER_PORT=8080

EXPOSE 8080

# Seed repos.toml from the example on first start if it is missing, then launch
# the web UI.
CMD ["sh", "-c", "[ -f /app/repos.toml ] || cp /app/repos.toml.example /app/repos.toml; exec python -m health_checker_agent.server"]
