FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim

WORKDIR /srv/notebook

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN useradd --system --create-home --uid 10001 notebook \
    && mkdir -p /data \
    && chown -R notebook:notebook /srv/notebook /data

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

USER notebook
ENV PATH="/srv/notebook/.venv/bin:${PATH}"
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
