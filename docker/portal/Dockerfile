FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim

# TODO: 実装確定時にnginxのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/portal

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && rm -f /etc/nginx/sites-enabled/default \
    && chown -R www-data:www-data /srv/portal

ENV PATH="/srv/portal/.venv/bin:${PATH}"
EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
