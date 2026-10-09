#!/usr/bin/env bash
# setup-nightly-update.sh — the daily job that keeps the nightly update channel rolling. A systemd USER timer, no sudo.
#
#   iso/setup-nightly-update.sh install     write the units and enable the daily timer
#   iso/setup-nightly-update.sh status      the timer, the last run, and what the nightly channel serves right now
#   iso/setup-nightly-update.sh run         build and publish now if main changed (through the same unit, so the log is the same)
#   iso/setup-nightly-update.sh remove      disable and delete the timer (the clone stays)
#
# The job (iso/nightly-update.sh) uses its own clone of GitHub main and the workstation's signing key and store credentials, like
# iso/publish-update.sh. Daily at 03:15 with Persistent=true: a run missed while the machine was off happens at the next boot.
# Installing it is a decision (it publishes to the nightly channel by itself); nothing runs it until you do.
set -Eeuo pipefail

DIR="${NIGHTLY_HOME:-$HOME/.local/share/noctraos-nightly}"
REPO_URL="${NIGHTLY_REPO_URL:-https://github.com/dazeb/noctraos.git}"
UNIT_DIR="${NIGHTLY_UNIT_DIR:-$HOME/.config/systemd/user}"
BASE="${NIGHTLY_PUBLIC_BASE:-https://dl.noctraos.dev/updates}"
say() { printf '%s\n' "$*"; }

install_units() {
  mkdir -p "$DIR" "$UNIT_DIR"
  [ -d "$DIR/repo/.git" ] || git clone -q "$REPO_URL" "$DIR/repo"
  # The runner script is fetched fresh from main by the job itself; this wrapper only gets it started.
  cat > "$DIR/run.sh" <<RUN
#!/usr/bin/env bash
set -Eeuo pipefail
git -C "$DIR/repo" fetch -q origin main
git -C "$DIR/repo" reset -q --hard origin/main
exec bash "$DIR/repo/iso/nightly-update.sh"
RUN
  chmod 755 "$DIR/run.sh"
  cat > "$UNIT_DIR/noctraos-nightly-update.service" <<UNIT
[Unit]
Description=Publish GitHub main to the NoctraOS nightly update channel when it changed

[Service]
Type=oneshot
ExecStart=$DIR/run.sh
Environment=SHLVL=2
TimeoutStartSec=90min
UNIT
  cat > "$UNIT_DIR/noctraos-nightly-update.timer" <<UNIT
[Unit]
Description=Daily NoctraOS nightly update

[Timer]
OnCalendar=*-*-* 03:15
Persistent=true
RandomizedDelaySec=20min

[Install]
WantedBy=timers.target
UNIT
  systemctl --user daemon-reload
}

case "${1:-}" in
  install)
    command -v jq >/dev/null && command -v git >/dev/null && command -v rclone >/dev/null && command -v python3 >/dev/null \
      || { say "needs git, jq, rclone and python3" >&2; exit 1; }
    [ -r "${NOCTRAOS_UPDATE_KEY:-$HOME/secrets/noctraos-update-signing}" ] || { say "no signing key at ~/secrets/noctraos-update-signing" >&2; exit 1; }
    install_units
    systemctl --user enable --now noctraos-nightly-update.timer >/dev/null
    say "installed: $(systemctl --user list-timers noctraos-nightly-update.timer --no-legend | awk '{print "next run", $1, $2, $3}')" ;;
  status)
    systemctl --user is-enabled noctraos-nightly-update.timer 2>&1 | sed 's/^/timer:  /'
    systemctl --user list-timers noctraos-nightly-update.timer --no-legend 2>/dev/null | awk '{print "next:   " $1, $2, $3}'
    systemctl --user show noctraos-nightly-update.service -p ActiveEnterTimestamp -p Result 2>/dev/null | sed 's/^/last:   /'
    printf 'public nightly '
    curl -fsS --max-time 20 "$BASE/nightly/manifest.json" 2>/dev/null | jq -r '"serial \(.serial), commit \(.commit[0:7]), \(.notes)"' 2>/dev/null || echo "no manifest" ;;
  run) systemctl --user start noctraos-nightly-update.service && say "done (see: journalctl --user -u noctraos-nightly-update -n 30)" ;;
  remove)
    systemctl --user disable --now noctraos-nightly-update.timer 2>/dev/null || true
    rm -f "$UNIT_DIR/noctraos-nightly-update.service" "$UNIT_DIR/noctraos-nightly-update.timer"
    systemctl --user daemon-reload; say "removed" ;;
  *) say "usage: setup-nightly-update.sh install|status|run|remove" >&2; exit 2 ;;
esac
