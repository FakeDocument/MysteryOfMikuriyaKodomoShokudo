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

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk locales \
    && sed -i 's/^# *ja_JP.UTF-8 UTF-8/ja_JP.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8

RUN useradd --create-home --shell /bin/bash player

COPY config/xstartup /home/player/.config/tigervnc/xstartup
COPY bin/nmap /usr/local/bin/nmap
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /home/player/.config/tigervnc/xstartup /usr/local/bin/nmap /entrypoint.sh \
    && chown -R player:player /home/player

WORKDIR /home/player

EXPOSE 6901

ENTRYPOINT ["/entrypoint.sh"]
