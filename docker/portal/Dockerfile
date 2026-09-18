FROM ghcr.io/astral-sh/uv:0.5.11-python3.12-bookworm-slim

# TODO: 実装確定時にnginxのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl util-linux samba \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/portal

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY samba/smb.conf /etc/samba/smb.conf
COPY samba/share/ /srv/samba/handoff/
COPY samba/handover/ /srv/samba/handover/
RUN useradd --system --user-group --no-create-home --shell /usr/sbin/nologin hozen_sync \
    && printf '%s\n%s\n' 'TideLog_2024' 'TideLog_2024' | smbpasswd -a -s hozen_sync \
    && chown -R root:hozen_sync /srv/samba/handoff \
    && find /srv/samba/handoff -type d -exec chmod 0750 {} + \
    && find /srv/samba/handoff -type f -exec chmod 0640 {} +

COPY app ./app
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && rm -f /etc/nginx/sites-enabled/default \
    && chown -R www-data:www-data /srv/portal

ENV PATH="/srv/portal/.venv/bin:${PATH}"
EXPOSE 80 445 8080

ENTRYPOINT ["/entrypoint.sh"]
