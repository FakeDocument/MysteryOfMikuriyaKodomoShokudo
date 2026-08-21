FROM debian:bookworm-slim

# TODO: 実装確定時にnginx/sambaのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx samba curl \
    && rm -rf /var/lib/apt/lists/*

COPY samba/smb.conf /etc/samba/smb.conf
COPY nginx.conf /etc/nginx/sites-available/default
COPY site/ /usr/share/nginx/html/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80 445

ENTRYPOINT ["/entrypoint.sh"]
