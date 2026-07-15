FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy runtime assets
COPY core/ core/
COPY engines/ engines/
COPY prompt/ prompt/
COPY skills/ skills/
COPY hooks/ hooks/
COPY plugins/ plugins/
COPY tasks/ tasks/
COPY ca_launcher.py ca_launcher.py
COPY config.json config.json
COPY setup.py setup.py

# Frontend build (optional — skip if dist/ is not present)
COPY web/frontend/dist/ web/frontend/dist/ 2>/dev/null || true

EXPOSE 8524

CMD ["python", "ca_launcher.py", "ui"]
