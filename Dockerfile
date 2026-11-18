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
COPY pyproject.toml uv.lock README.md setup.py ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# Copy runtime assets
COPY core/ core/
COPY engines/ engines/
COPY prompt/ prompt/
COPY skills/ skills/
COPY hooks/ hooks/
COPY plugins/ plugins/
COPY tasks/ tasks/
COPY ca_launcher.py config.example.json ./

# The release pipeline builds the frontend before building this image.
COPY web/frontend/dist/ web/frontend/dist/

# Install the CodeAgent package itself into .venv now that sources exist
RUN uv sync --frozen --no-dev

EXPOSE 8524

ENV CA_UI_HOST=0.0.0.0
CMD ["uv", "run", "--no-sync", "python", "ca_launcher.py", "ui"]
