#!/usr/bin/env bash
# desktops: any
# Pending the flavour split (docs/flavours.md): the Nautilus skel scripts belong to the GNOME desktop code.
# Module 07: persistence — /etc/skel defaults for new users + noc management CLI.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

log "Syncing defaults into /etc/skel (applies to every user created from now on)..."
sudo mkdir -p \
  /etc/skel/.config/mise \
  /etc/skel/.config/copyq \
  /etc/skel/.config/herdr \
  /etc/skel/.config/btop/themes \
  /etc/skel/.config/autostart \
  /etc/skel/.config/Code/User \
  /etc/skel/.continue \
  /etc/skel/.local/share/nautilus/scripts

sudo install -m 644 "$REPO_ROOT/configs/mise/config.toml" \
  /etc/skel/.config/mise/config.toml
sudo install -m 644 "$REPO_ROOT/configs/vscode/continue_config.yaml" \
  /etc/skel/.continue/config.yaml
sudo install -m 644 "$REPO_ROOT/configs/vscode/settings.json" \
  /etc/skel/.config/Code/User/settings.json
for old in Open_in_VSCodium Ask_AI_to_Explain Open_Terminal_Here Open_in_VS_Code; do
  sudo rm -f "/etc/skel/.local/share/nautilus/scripts/$old"
done
sudo install -m 644 "$REPO_ROOT/configs/copyq/copyq.conf" \
  /etc/skel/.config/copyq/copyq.conf
sudo install -m 644 "$REPO_ROOT/configs/theme/herdr.toml" \
  /etc/skel/.config/herdr/config.toml
sudo install -m 644 "$REPO_ROOT/configs/theme/noctraos-btop.theme" \
  /etc/skel/.config/btop/themes/noctraos.theme
if [ ! -f /etc/skel/.config/btop/btop.conf ]; then
  printf 'color_theme = "noctraos"\n' | sudo tee /etc/skel/.config/btop/btop.conf >/dev/null
fi
sudo install -m 644 "$REPO_ROOT/configs/autostart/copyq.desktop" \
  /etc/skel/.config/autostart/copyq.desktop
sudo python3 "$REPO_ROOT/scripts/seed-password-store.py" /etc/skel >/dev/null \
  || warn "Could not seed the keyring-free password store for new users"
for src in "$REPO_ROOT/configs/nautilus-scripts/"*; do
  [ -f "$src" ] || continue
  sudo install -m 755 "$src" "/etc/skel/.local/share/nautilus/scripts/$(basename "$src")"
done
sudo chmod -R go+rX /etc/skel/.config /etc/skel/.continue /etc/skel/.local
# ...except the keyring directory, which stays private to the account.
[ -d /etc/skel/.local/share/keyrings ] && sudo chmod -R go-rwx /etc/skel/.local/share/keyrings

log "Installing noc management CLI..."
# Clean break from the pre-rename CLI name (zom → noc).
sudo rm -f /usr/local/bin/zom /usr/local/bin/zom-menu /usr/local/bin/zom-gpu \
  /usr/local/share/applications/zom-menu.desktop
sudo install -m 755 "$REPO_ROOT/bin/noc" /usr/local/bin/noc
sudo install -m 755 "$REPO_ROOT/bin/noc-gpu" /usr/local/bin/noc-gpu
sudo install -m 755 "$REPO_ROOT/bin/noc-upstream" /usr/local/bin/noc-upstream
sudo install -m 755 "$REPO_ROOT/bin/noc-accounts" /usr/local/bin/noc-accounts
sudo install -m 755 "$REPO_ROOT/bin/noc-disk" /usr/local/bin/noc-disk
sudo install -m 755 "$REPO_ROOT/bin/noc-agent-skills" /usr/local/bin/noc-agent-skills
# Programs other modules installed (noctraos-hermes, noctraos-agent, the welcome app, ...) are refreshed in place, so an update
# that changes one reaches machines that already have it. Only programs that are already there: a new one arrives with its own
# module (menu entry, icon). This copies files only; it never touches a person's settings.
for program in "$REPO_ROOT"/bin/noctraos-*; do
  [ -f "$program" ] && [ -f "/usr/local/bin/$(basename "$program")" ] || continue
  cmp -s "$program" "/usr/local/bin/$(basename "$program")" \
    || sudo install -m 755 "$program" "/usr/local/bin/$(basename "$program")"
done

log "Installing the Control Panel (replaces the old zenity noc-menu)..."
# Clean break: the zenity panel and its launcher are gone, not aliased.
sudo rm -f /usr/local/bin/noc-menu /usr/local/share/applications/noc-menu.desktop
sudo mkdir -p /usr/local/share/noctraos-control
for f in "$REPO_ROOT"/control/*.py; do
  sudo install -m 644 "$f" "/usr/local/share/noctraos-control/$(basename "$f")"
done
sudo install -m 755 "$REPO_ROOT/bin/noctraos-control" /usr/local/bin/noctraos-control
# Launchers and icons are refreshed here too (not only by module 06): an update re-runs this module, and a changed launcher
# or icon should reach machines that already have it. install_launchers copies only what differs and touches no setting.
install_launchers "$REPO_ROOT"

log "Installing the privileged helper (one polkit prompt for updates and repairs)..."
sudo install -d -m 755 /usr/local/libexec/noctraos
sudo install -m 755 "$REPO_ROOT/bin/noc-privileged" /usr/local/libexec/noctraos/noc-privileged
sudo install -m 644 "$REPO_ROOT/configs/polkit/dev.noctraos.privileged.policy" \
  /usr/share/polkit-1/actions/dev.noctraos.privileged.policy
log "Installing the NoctraOS updater (signed, staged updates of the NoctraOS layer; docs/updates.md)..."
sudo install -m 755 "$REPO_ROOT/bin/noc-selfupdate" /usr/local/libexec/noctraos/noc-selfupdate
sudo install -d -m 755 /usr/local/share/noctraos /etc/noctraos
sudo install -m 644 "$REPO_ROOT/configs/update/update-signers" /usr/local/share/noctraos/update-signers
# The channel is the person's choice and is never overwritten; the mirror list stays in the code so an update can change it.
if [ ! -f /etc/noctraos/update.json ]; then
  printf '{"channel": "stable"}\n' | sudo tee /etc/noctraos/update.json >/dev/null
fi
# A daily look at one small signed file (a plain GET, nothing is sent), and a login-time catch-up for per-account migrations.
for unit in noctraos-update-check.service noctraos-update-check.timer; do
  sudo install -D -m 644 "$REPO_ROOT/configs/systemd/$unit" "/etc/systemd/user/$unit"
done
if [ ! -L /etc/systemd/user/timers.target.wants/noctraos-update-check.timer ]; then
  sudo systemctl --global enable noctraos-update-check.timer >/dev/null 2>&1 \
    || warn "Could not enable the NoctraOS update check timer"
fi
sudo install -D -m 644 "$REPO_ROOT/configs/autostart/noctraos-update-migrate.desktop" \
  /etc/xdg/autostart/noctraos-update-migrate.desktop
# One notice per new amount of unused disk space (a virtual disk that was enlarged after install); nothing changes
# until the person agrees in the Control Panel.
sudo install -D -m 644 "$REPO_ROOT/configs/autostart/noctraos-disk-notice.desktop" \
  /etc/xdg/autostart/noctraos-disk-notice.desktop

# The helper re-runs install modules as root, so it must never run them from a clone the user can
# edit: keep a root-owned snapshot of what the modules read and run only that. Refreshed only when
# the content changed, so a second run is a no-op.
SNAPSHOT=/usr/local/share/noctraos/repo
STAGE="$(mktemp -d)"
chmod 755 "$STAGE"   # mktemp makes it 0700; the snapshot must be traversable so the diff below can read it
trap 'rm -rf "$STAGE"' EXIT
for item in VERSION install.sh install bin configs scripts assets help extensions branding search control migrations; do
  [ -e "$REPO_ROOT/$item" ] && cp -a "$REPO_ROOT/$item" "$STAGE/"
done
rm -rf "$STAGE/assets/promo" "$STAGE/assets/social"
if [ -d "$SNAPSHOT" ] && diff -rq "$STAGE" "$SNAPSHOT" >/dev/null 2>&1; then
  log "Root-owned module snapshot is current."
else
  sudo rm -rf "$SNAPSHOT.new"
  sudo mkdir -p "$(dirname "$SNAPSHOT")"
  sudo cp -a "$STAGE" "$SNAPSHOT.new"
  sudo chown -R root:root "$SNAPSHOT.new"
  sudo chmod -R go-w "$SNAPSHOT.new"
  sudo rm -rf "$SNAPSHOT"
  sudo mv "$SNAPSHOT.new" "$SNAPSHOT"
  log "Root-owned module snapshot written to $SNAPSHOT."
fi

# The NoctraOS skill for the coding agents (Hermes, Codex, Claude Code): copied to ~/.agents/skills from the snapshot just
# written, linked where an agent is already installed. Content only, no agent setting is touched; a copy the person edited,
# or ~/.config/noctraos/no-agent-skills, is respected. Other accounts catch up through migrations/user/0002.
as_user /usr/local/bin/noc-agent-skills install || warn "Could not install the NoctraOS agent skill (noc agent-skills install retries)"

log "Persistence complete: new users inherit mise, Continue and Nautilus script defaults."
log "Manage the workstation with: noc (CLI) or the NoctraOS Control Panel (GUI)."
