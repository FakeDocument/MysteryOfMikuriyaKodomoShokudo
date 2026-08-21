FROM kalilinux/kali-rolling

# TODO: 実装確定時に各パッケージのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xfce4 xfce4-terminal dbus-x11 \
        tigervnc-standalone-server tigervnc-common tigervnc-tools \
        novnc websockify \
        firefox-esr mousepad \
        nmap gobuster smbclient curl \
    && rm -rf /var/lib/apt/lists/*

# DIRB's bundled common.txt is the standard discovery list used by this CTF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends dirb \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash player

COPY config/xstartup /home/player/.config/tigervnc/xstartup
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /home/player/.config/tigervnc/xstartup /entrypoint.sh \
    && chown -R player:player /home/player

EXPOSE 6901

ENTRYPOINT ["/entrypoint.sh"]
