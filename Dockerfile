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
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Copy runtime assets
COPY core/ core/
COPY engines/ engines/
COPY prompt/ prompt/
COPY skills/ skills/
COPY hooks/ hooks/
COPY plugins/ plugins/
COPY tasks/ tasks/
COPY ca_launcher.py ca_launcher.py

# The release pipeline builds the frontend before building this image.
COPY web/frontend/dist/ web/frontend/dist/

EXPOSE 8524

ENV CA_UI_HOST=0.0.0.0
CMD ["python", "ca_launcher.py", "ui"]
