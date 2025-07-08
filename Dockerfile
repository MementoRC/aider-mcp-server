# Use a Python base image
FROM python:3.12-bookworm-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install pixi
RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH="/root/.pixi/bin:${PATH}"

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY README.md ./

# Install dependencies with pixi
RUN pixi install --locked

# Production stage
FROM python:3.12-bookworm-slim

# Install git (required for aider operations)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 app

# Set working directory
WORKDIR /app

# Copy pixi environment from builder
COPY --from=builder --chown=app:app /root/.pixi /home/app/.pixi
COPY --from=builder --chown=app:app /app /app

# Set environment variables
ENV PATH="/home/app/.pixi/bin:${PATH}"
ENV PYTHONPATH="/app/src"

# Switch to non-root user
USER app

# Default command
CMD ["pixi", "run", "mcp-server"]