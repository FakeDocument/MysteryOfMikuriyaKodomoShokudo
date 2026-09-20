FROM debian:bookworm-slim

# TODO: 実装確定時にnginx/sambaのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx samba curl python3 python3-jinja2 \
    && rm -rf /var/lib/apt/lists/*

COPY samba/smb.conf /etc/samba/smb.conf
COPY samba/share/ /srv/samba/staff/
COPY nginx.conf /etc/nginx/sites-available/default
COPY site/ /usr/share/nginx/html/
COPY webmail/ /opt/mikuriya-webmail/
COPY entrypoint.sh /entrypoint.sh
RUN useradd --system --user-group --no-create-home --shell /usr/sbin/nologin kanzaki \
    && printf '%s\n%s\n' 'Kanzaki2018' 'Kanzaki2018' | smbpasswd -a -s kanzaki \
    && chown -R root:kanzaki /srv/samba/staff \
    && find /srv/samba/staff -type d -exec chmod 0750 {} + \
    && find /srv/samba/staff -type f -exec chmod 0640 {} + \
    && chmod +x /entrypoint.sh /opt/mikuriya-webmail/app.py

EXPOSE 80 445

ENTRYPOINT ["/entrypoint.sh"]
