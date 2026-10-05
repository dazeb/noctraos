#!/usr/bin/env bash
# vm-sysprep.sh — prepare a fully provisioned NoctraOS VM for export as a
# downloadable disk image. Run as root INSIDE the VM, then power it off and
# export the disk (see docs/vm-image.md).
#
# Removes what must not ship in a shared image: machine identity, SSH host keys,
# the per-user Hermes identity/history, shell history, logs and caches. Keeps the
# installed system, the Ollama models and the Hermes runtime + app.
#
# DESTRUCTIVE to the VM's identity: do not run it on a machine you want to keep.
#   sudo bash vm-sysprep.sh [username]        (default: noctraos)
set -Eeuo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
# Never on real hardware: this erases the machine's identity and history.
if ! systemd-detect-virt -q 2>/dev/null; then
  echo "refusing: this is not a virtual machine (systemd-detect-virt found no hypervisor)" >&2
  exit 1
fi
if [ "${NOCTRAOS_SYSPREP_YES:-}" != "1" ]; then
  echo "This wipes this machine's identity and history so it can be exported as an image."
  read -r -p "Type 'sysprep' to continue: " ans
  [ "$ans" = "sysprep" ] || { echo "aborted"; exit 1; }
fi

USER_NAME="${1:-noctraos}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
[ -n "$HOME_DIR" ] && [ -d "$HOME_DIR" ] || { echo "no such user/home: $USER_NAME" >&2; exit 1; }
log() { printf '[sysprep] %s\n' "$*"; }

# The desktop session and Hermes must not be running while we delete their state.
pkill -u "$USER_NAME" -x Hermes 2>/dev/null || true
pkill -u "$USER_NAME" -x hermes 2>/dev/null || true
sleep 2

log "Hermes: removing the per-user identity, history and Electron profile"
H="$HOME_DIR/.hermes"
rm -f  "$H"/auth.json "$H"/auth.lock "$H"/state.db* "$H"/.env \
       "$H"/.noctraos-onboarded "$H"/.noctraos-greeted "$H"/.noctraos-greet-tries
rm -rf "$H"/sessions "$H"/logs "$H"/memories "$H"/cache "$H"/audio_cache "$H"/checkpoints \
       "$H"/browser-profile "$HOME_DIR/.config/Hermes"
# Keep config.yaml (free-tier primary, Ollama fallback, VM Electron flags) and the
# seed marker so the wrapper does not re-seed over it.

log "shell history, caches"
rm -f "$HOME_DIR"/.bash_history /root/.bash_history "$HOME_DIR"/.python_history "$HOME_DIR"/.viminfo
rm -rf "$HOME_DIR"/.npm/_cacache "$HOME_DIR"/.npm/_logs "$HOME_DIR"/.cache/pip "$HOME_DIR"/.cache/uv
rm -rf "$HOME_DIR"/.local/share/noctraos-firstboot.log "$HOME_DIR"/.local/share/Trash
rm -f  /tmp/noctraos-install-*.log

log "SSH host keys: removed now, regenerated on first boot"
rm -f /etc/ssh/ssh_host_*
cat > /etc/systemd/system/noctraos-ssh-hostkeys.service <<'UNIT'
[Unit]
Description=Generate SSH host keys on first boot of a NoctraOS image
Before=ssh.service ssh.socket
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
UNIT
systemctl enable noctraos-ssh-hostkeys.service >/dev/null 2>&1 || true

log "logs, installer leftovers, apt cache"
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-time=1s >/dev/null 2>&1 || true
find /var/log -type f \( -name '*.gz' -o -name '*.[0-9]' -o -name '*.old' \) -delete 2>/dev/null || true
find /var/log -type f -exec truncate -s 0 {} + 2>/dev/null || true
rm -rf /var/log/installer /var/lib/ubiquity /var/crash/* /tmp/* /var/tmp/* 2>/dev/null || true
apt-get clean
rm -rf /var/lib/apt/lists/*

log "machine identity: cleared (systemd generates a new one on first boot)"
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -sf /etc/machine-id /var/lib/dbus/machine-id

log "trimming free space so the exported image stays small"
sync
fstrim -av 2>&1 | sed 's/^/[sysprep] /' || true

# Hard checks: refuse to call it ready if anything identifying is left.
bad=0
[ ! -e "$H/auth.json" ]                    || { echo "STILL PRESENT: $H/auth.json" >&2; bad=1; }
[ ! -e "$H/state.db" ]                     || { echo "STILL PRESENT: $H/state.db" >&2; bad=1; }
ls /etc/ssh/ssh_host_* >/dev/null 2>&1     && { echo "STILL PRESENT: ssh host keys" >&2; bad=1; }
[ ! -s /etc/machine-id ]                   || { echo "machine-id not empty" >&2; bad=1; }
[ "$bad" -eq 0 ] || exit 1

log "READY. Power off now (sudo poweroff) and export the disk. Do not boot this VM again before exporting."
