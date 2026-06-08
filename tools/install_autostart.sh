#!/usr/bin/env bash
#
# Endymion autostart installer.
#
# Run ONCE on the Pi to create and enable a systemd user service that
# launches main.py at boot. Idempotent: safe to re-run after pulling an
# updated version of this script — the service file is regenerated each
# time. Re-running will NOT restart a currently-running service; do that
# manually with `systemctl --user restart endymion`.
#
# Usage (on the Pi, from the repo root or anywhere):
#     bash tools/install_autostart.sh
#
# What this does:
#   1. Auto-detects the active Wayland socket name (wayland-0, wayland-1, …).
#   2. Writes ~/.config/systemd/user/endymion.service with absolute paths
#      baked from this Pi's environment.
#   3. Reloads systemd-user, enables the unit, and enables user linger
#      (so the user manager starts at boot, before any graphical login).
#
# See docs/SPEC-autostart.md for the design and the rationale behind
# each non-obvious choice (graphical-session.target rejection, Wayland
# socket polling via ExecStartPre, Restart=always, SDL_VIDEODRIVER).

set -euo pipefail

# --- Resolve paths ---------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$REPO_ROOT/main.py" ]; then
    echo "ERROR: $REPO_ROOT/main.py not found." >&2
    echo "This script must live in <repo>/tools/. Aborting." >&2
    exit 1
fi
if [ ! -x "$REPO_ROOT/venv/bin/python" ]; then
    echo "ERROR: $REPO_ROOT/venv/bin/python not found or not executable." >&2
    echo "Create the venv first: python3 -m venv venv && pip install -r requirements.txt" >&2
    exit 1
fi
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "ERROR: $REPO_ROOT/.env not found." >&2
    echo "The service uses .env as its EnvironmentFile. Create it before installing." >&2
    exit 1
fi

USER_ID=$(id -u)
RUNTIME_DIR="/run/user/$USER_ID"

# --- Auto-detect Wayland socket -------------------------------------------
#
# On this Pi (labwc + Pi OS Bookworm) the socket is currently wayland-0,
# but a fresh OS image or multi-session state could produce a different
# name. Detect rather than hard-code so the installer works across rebuilds.

WAYLAND_SOCK_PATH=""
if [ -d "$RUNTIME_DIR" ]; then
    # Find any wayland-N socket (ignore .lock files).
    for candidate in "$RUNTIME_DIR"/wayland-*; do
        [ -S "$candidate" ] || continue
        WAYLAND_SOCK_PATH="$candidate"
        break
    done
fi

if [ -z "$WAYLAND_SOCK_PATH" ]; then
    echo "ERROR: No Wayland socket found under $RUNTIME_DIR." >&2
    echo "" >&2
    echo "Run this installer from an active graphical session — open a" >&2
    echo "terminal on the Pi's desktop (or SSH after the compositor has" >&2
    echo "started). The socket appears once labwc is running." >&2
    exit 1
fi

WAYLAND_DISPLAY_VALUE="$(basename "$WAYLAND_SOCK_PATH")"

# --- Sanity-check the compositor -------------------------------------------

if ! pgrep -x labwc > /dev/null 2>&1; then
    echo "WARN: labwc is not currently running on this Pi." >&2
    echo "      The service file will still be installed, but autostart" >&2
    echo "      assumes the compositor matches the value of WAYLAND_DISPLAY" >&2
    echo "      detected: $WAYLAND_DISPLAY_VALUE" >&2
fi

# --- Compose the service file ----------------------------------------------

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/endymion.service"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Endymion interactive video installation
Documentation=https://github.com/Great-Bucket/Endymion
# graphical-session.target is intentionally NOT used:
# Pi OS Bookworm + labwc autologin does not activate that target, so any
# Wants/WantedBy that references it would prevent autostart.
# Instead we depend on default.target (always active for lingering users)
# and gate the actual app start on the Wayland socket existing — see
# ExecStartPre below.
After=default.target

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT

# .env contains all KINECT_*, EFFECTS, HALF_RES_EFFECTS, EMPTY_CAVE_DARK,
# etc. Plain KEY=value format — no shell expansion. See docs/SPEC-autostart.md
# §5 for compatibility notes.
EnvironmentFile=$REPO_ROOT/.env

# Wayland / SDL display environment. WAYLAND_DISPLAY value was auto-detected
# by the installer at install time (see install_autostart.sh).
Environment=WAYLAND_DISPLAY=$WAYLAND_DISPLAY_VALUE
Environment=XDG_RUNTIME_DIR=$RUNTIME_DIR
# SDL2 / pygame: be explicit about the Wayland backend so SDL doesn't
# fall back to dummy or x11 on a labwc-only Pi.
Environment=SDL_VIDEODRIVER=wayland
# Flush Python output to journald in real time so journalctl -f shows
# pygame / print output without buffering.
Environment=PYTHONUNBUFFERED=1

# Wait for the Wayland socket to actually exist before launching the app.
# default.target may activate before labwc has had time to start; the app
# would otherwise fail immediately on SDL_VideoInit. Poll once a second
# for up to 60 s, then give up and let systemd report the failure.
ExecStartPre=/bin/bash -c 'for i in {1..60}; do [ -S "\$XDG_RUNTIME_DIR/\$WAYLAND_DISPLAY" ] && exit 0; sleep 1; done; echo "Wayland socket \$XDG_RUNTIME_DIR/\$WAYLAND_DISPLAY did not appear within 60s" >&2; exit 1'

ExecStart=$REPO_ROOT/venv/bin/python main.py

# Always restart, including on clean exit (accidental Q/Esc). Calibration
# stops via systemctl stop, which systemd correctly does NOT restart.
# Default StartLimitIntervalSec=10s + StartLimitBurst=5 guard against
# tight restart loops on persistent failure — service goes to "failed"
# after 5 restart attempts in 10 s.
Restart=always
RestartSec=10s

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# --- Enable, reload, and arrange for boot-time start -----------------------

systemctl --user daemon-reload
systemctl --user enable endymion.service

# Linger keeps the user systemd manager alive across reboots even before
# graphical login. Required for autostart-at-boot semantics. Idempotent.
if ! loginctl show-user "$USER_ID" 2>/dev/null | grep -q '^Linger=yes'; then
    sudo loginctl enable-linger "$USER"
    echo "Linger enabled for $USER."
fi

# --- Done ------------------------------------------------------------------

echo
echo "Endymion autostart installed."
echo "  Service file : $SERVICE_FILE"
echo "  Wayland disp : $WAYLAND_DISPLAY_VALUE (auto-detected)"
echo "  Runtime dir  : $RUNTIME_DIR"
echo
echo "Manage the service over SSH with:"
echo "  systemctl --user status endymion"
echo "  systemctl --user stop    endymion   # for on-site calibration"
echo "  systemctl --user start   endymion"
echo "  systemctl --user restart endymion   # recapture Kinect background"
echo "  journalctl  --user -u endymion -f   # live log"
echo
echo "Start now:    systemctl --user start endymion"
echo "Or reboot to verify autostart behaviour end-to-end."
