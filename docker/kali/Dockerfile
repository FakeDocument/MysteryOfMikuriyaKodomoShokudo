FROM kalilinux/kali-rolling

# TODO: 実装確定時に各パッケージのバージョンをapt pinningで明示的に固定する。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xfce4 xfce4-terminal dbus-x11 \
        tigervnc-standalone-server tigervnc-common tigervnc-tools \
        novnc websockify \
        firefox-esr firefox-esr-l10n-ja mousepad \
        nmap gobuster smbclient curl \
    && rm -rf /var/lib/apt/lists/*

# DIRB's bundled common.txt is the standard discovery list used by this CTF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends dirb \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-noto-cjk locales \
        fcitx5 fcitx5-mozc fcitx5-frontend-gtk3 \
    && sed -i 's/^# *ja_JP.UTF-8 UTF-8/ja_JP.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8 \
    GTK_IM_MODULE=fcitx \
    QT_IM_MODULE=fcitx \
    XMODIFIERS=@im=fcitx

RUN useradd --create-home --shell /bin/bash player

COPY config/xstartup /home/player/.config/tigervnc/xstartup
COPY config/fcitx5-autostart.desktop /home/player/.config/autostart/fcitx5.desktop
COPY config/fcitx5-config /home/player/.config/fcitx5/config
COPY config/fcitx5-profile /home/player/.config/fcitx5/profile
COPY config/firefox-policies.json /usr/share/firefox-esr/distribution/policies.json
COPY novnc/sushictf-note.css /usr/share/novnc/app/sushictf-note.css
COPY novnc/sushictf-note.js /usr/share/novnc/app/sushictf-note.js
COPY bin/nmap /usr/local/bin/nmap
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's#<head>#<head>\n    <meta charset="utf-8">#' /usr/share/novnc/vnc.html \
    && sed -i 's#</head>#  <link rel="stylesheet" href="app/sushictf-note.css">\n</head>#' /usr/share/novnc/vnc.html \
    && sed -i 's#</body>#  <script src="app/sushictf-note.js" charset="utf-8"></script>\n</body>#' /usr/share/novnc/vnc.html
RUN chmod +x /home/player/.config/tigervnc/xstartup /usr/local/bin/nmap /entrypoint.sh \
    && chown -R player:player /home/player

WORKDIR /home/player

EXPOSE 6901

ENTRYPOINT ["/entrypoint.sh"]
