#!/usr/bin/env bash
#
# Endymion soak-test Pi health poller.
#
# Polls the Pi over SSH every 30 seconds for the given number of minutes
# and writes a one-line-per-poll log to logs/soak_monitor_<timestamp>.log.
# Never exits on a single poll failure — logs UNREACHABLE, sleeps, continues.
#
# Canonical invocation (prevents Mac sleep / lid-close during the run):
#     caffeinate -i ./tools/pi_monitor.sh 200
#
# Args:
#     $1 — duration in minutes (default: 360 = 6h, ≥1.5× the planned
#          3-hour event with comfortable headroom for over-running soaks)
#
# See docs/SPEC-monitoring.md for the full design.

set -uo pipefail   # NOT -e — we want to continue on individual poll failures

DURATION_MIN="${1:-360}"
INTERVAL_SEC=30
PI_HOST="box1@raspberrypi.local"

# SSH options — all three required for an unattended 3-hour run.
SSH_OPTS=(
    -o ConnectTimeout=5         # fail fast on hung connections
    -o ServerAliveInterval=10   # detect dead connections during the command
    -o BatchMode=yes            # never prompt for a password — fail instead
)

# Alert thresholds (see spec §Alert conditions)
TEMP_WARN_C=80     # Pi 5 soft-throttles at 80, hard-throttles at 85
MEM_WARN_MB=200

# Locate the project root + logs directory relative to this script.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/soak_monitor_${TIMESTAMP}.log"

# Write header (with a trailing # so it's grep-able by `grep -v '^#'`).
printf '# Endymion soak monitor — duration=%dmin interval=%ds host=%s\n' \
    "$DURATION_MIN" "$INTERVAL_SEC" "$PI_HOST" >> "$LOG_FILE"
printf '# Started: %s\n' "$(date -Iseconds 2>/dev/null || date)" >> "$LOG_FILE"
printf '# Log file: %s\n' "$LOG_FILE" >> "$LOG_FILE"

echo "[pi_monitor] Logging to: $LOG_FILE"
echo "[pi_monitor] Duration: ${DURATION_MIN} min, interval: ${INTERVAL_SEC}s"

END_TS=$(( $(date +%s) + DURATION_MIN * 60 ))

while [ "$(date +%s)" -lt "$END_TS" ]; do
    POLL_START=$(date +%s)
    NOW=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)

    # Single SSH session runs all probes; we parse on the Mac.
    # stderr suppressed — connection errors fall through to empty output.
    REMOTE_OUTPUT=$(
        ssh "${SSH_OPTS[@]}" "$PI_HOST" '
            vcgencmd measure_temp 2>/dev/null
            vcgencmd get_throttled 2>/dev/null
            free -m | awk "/^Mem:/ {print \"FREE_MEM used=\" \$3 \" avail=\" \$7}"
            pgrep -f "python.*main\.py" > /dev/null && echo "MAIN=YES" || echo "MAIN=NO"
        ' 2>/dev/null
    ) || true

    if [ -z "$REMOTE_OUTPUT" ]; then
        printf '%s\tUNREACHABLE\n' "$NOW" >> "$LOG_FILE"
    else
        # Parse fields out of the combined output.
        TEMP=$(printf '%s\n' "$REMOTE_OUTPUT" | sed -n "s/^temp=\\([0-9.]*\\).*/\\1/p" | head -n1)
        THROTTLE=$(printf '%s\n' "$REMOTE_OUTPUT" | sed -n 's/^throttled=\(0x[0-9a-fA-F]*\).*/\1/p' | head -n1)
        MEM_USED=$(printf '%s\n' "$REMOTE_OUTPUT" | sed -n 's/^FREE_MEM used=\([0-9]*\) avail=.*/\1/p' | head -n1)
        # We report "available" (free -m field 7) as mem_free — the actually-usable
        # memory headroom, not the misleading kernel "free" excluding cache.
        MEM_FREE=$(printf '%s\n' "$REMOTE_OUTPUT" | sed -n 's/^FREE_MEM .*avail=\([0-9]*\).*/\1/p' | head -n1)
        MAIN=$(printf '%s\n' "$REMOTE_OUTPUT" | sed -n 's/^MAIN=\([A-Z]*\).*/\1/p' | head -n1)

        # Defaults if any field failed to parse (Pi answered but in an unexpected shape).
        TEMP="${TEMP:-?}"
        THROTTLE="${THROTTLE:-?}"
        MEM_USED="${MEM_USED:-?}"
        MEM_FREE="${MEM_FREE:-?}"
        MAIN="${MAIN:-?}"

        printf '%s\ttemp=%sC\tthrottled=%s\tmem_used=%sMB\tmem_free=%sMB\tmain_running=%s\n' \
            "$NOW" "$TEMP" "$THROTTLE" "$MEM_USED" "$MEM_FREE" "$MAIN" >> "$LOG_FILE"

        # Alert conditions — each emits its own WARNING line for easy grep / count.
        if [ "$TEMP" != "?" ] && awk -v t="$TEMP" -v lim="$TEMP_WARN_C" 'BEGIN { exit !(t+0 >= lim+0) }'; then
            printf '%s\tWARNING\ttemp %sC >= %dC\n' "$NOW" "$TEMP" "$TEMP_WARN_C" >> "$LOG_FILE"
        fi

        # Throttle low 4 bits non-zero = currently throttling. 0x50000 means
        # "previously throttled" — informational, not an alert.
        if [ "$THROTTLE" != "?" ]; then
            # Bash supports hex arithmetic via $(( ))
            ACTIVE_BITS=$(( THROTTLE & 0xF ))
            if [ "$ACTIVE_BITS" -ne 0 ]; then
                printf '%s\tWARNING\tthrottle active (%s)\n' "$NOW" "$THROTTLE" >> "$LOG_FILE"
            fi
        fi

        if [ "$MEM_FREE" != "?" ] && [ "$MEM_FREE" -lt "$MEM_WARN_MB" ] 2>/dev/null; then
            printf '%s\tWARNING\tmem_free %sMB < %dMB\n' "$NOW" "$MEM_FREE" "$MEM_WARN_MB" >> "$LOG_FILE"
        fi

        if [ "$MAIN" != "YES" ]; then
            printf '%s\tWARNING\tmain.py not running\n' "$NOW" >> "$LOG_FILE"
        fi
    fi

    # Sleep until the next interval boundary, accounting for poll duration.
    POLL_END=$(date +%s)
    POLL_TOOK=$(( POLL_END - POLL_START ))
    SLEEP_FOR=$(( INTERVAL_SEC - POLL_TOOK ))
    if [ "$SLEEP_FOR" -gt 0 ]; then
        sleep "$SLEEP_FOR"
    fi
done

# Visible end marker so the boundary between "monitored window" and
# "no further telemetry" is unambiguous when scrolling the log.
printf '%s\t[MONITOR ENDED — no further telemetry]\n' \
    "$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)" >> "$LOG_FILE"
printf '# Ended: %s\n' "$(date -Iseconds 2>/dev/null || date)" >> "$LOG_FILE"
echo "[pi_monitor] Done. Log: $LOG_FILE"
