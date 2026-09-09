#!/bin/bash
# Fullscreen dashboard kiosk for the Pi's attached monitor.
# Waits until the dashboard service answers, then launches Chromium in kiosk
# mode. Started at desktop login via ~/.config/autostart/puzzle-kiosk.desktop.

URL="http://127.0.0.1:8000"

# The dashboard service may still be starting (camera/GPIO init, restarts).
for _ in $(seq 1 60); do
    curl -fsS -o /dev/null "$URL" && break
    sleep 2
done

# Raspberry Pi OS ships the browser as chromium-browser (Bookworm) or chromium (Trixie).
BROWSER=$(command -v chromium-browser || command -v chromium)
if [ -z "$BROWSER" ]; then
    echo "puzzle-kiosk: chromium not found" >&2
    exit 1
fi

exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars \
    --disable-session-crashed-bubble --incognito "$URL"
