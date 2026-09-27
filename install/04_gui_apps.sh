#!/usr/bin/env bash
# Module 04: mouse-driven GUI applications — VSCodium, Mission Center, Chatbox.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# ---- VSCodium (official community apt repo; CDN is download.vscodium.com) ------
if have codium; then
  log "OK: VSCodium already installed ($(codium --version 2>/dev/null | head -n 1))"
else
  log "Installing VSCodium (official apt repository)..."
  curl -fsSL https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/raw/master/pub.gpg \
    | gpg --dearmor \
    | sudo tee /usr/share/keyrings/vscodium-archive-keyring.gpg >/dev/null
  echo 'deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/vscodium-archive-keyring.gpg] https://download.vscodium.com/debs vscodium main' \
    | sudo tee /etc/apt/sources.list.d/vscodium.list >/dev/null
  sudo apt-get update -y
  apt_install codium
fi

# ---- extensions (per-extension idempotence) --------------------------------------
installed_exts="$(as_user codium --list-extensions 2>/dev/null || true)"
while IFS= read -r ext; do
  case "$ext" in ''|'#'*) continue ;; esac
  if grep -qx "$ext" <<<"$installed_exts"; then
    log "OK: extension already installed: $ext"
  else
    log "Installing VSCodium extension: $ext"
    as_user codium --install-extension "$ext" || warn "Extension install failed: $ext"
  fi
done < "$REPO_ROOT/configs/vscodium/extensions.list"

# ---- settings + Continue.dev → local Ollama ---------------------------------------
as_user mkdir -p "$TARGET_HOME/.config/VSCodium/User"
if as_user test -f "$TARGET_HOME/.config/VSCodium/User/settings.json"; then
  log "OK: VSCodium settings already present"
else
  log "Installing VSCodium settings..."
  sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
    "$REPO_ROOT/configs/vscodium/settings.json" \
    "$TARGET_HOME/.config/VSCodium/User/settings.json"
fi

# Existing installs keep their editor preferences. Add only palette keys that
# have not been customized by the user.
if ! as_user python3 - "$REPO_ROOT/configs/vscodium/settings.json" \
  "$TARGET_HOME/.config/VSCodium/User/settings.json" <<'PYEOF'; then
import json
import pathlib
import sys

template = json.loads(pathlib.Path(sys.argv[1]).read_text())
path = pathlib.Path(sys.argv[2])
settings = json.loads(path.read_text())
colors = settings.setdefault("workbench.colorCustomizations", {})
changed = False
for key, value in template["workbench.colorCustomizations"].items():
    if key not in colors:
        colors[key] = value
        changed = True
if changed:
    path.write_text(json.dumps(settings, indent=2) + "\n")
PYEOF
  warn "Could not merge Zorin AI colors into VSCodium settings"
fi

if as_user test -f "$TARGET_HOME/.continue/config.yaml"; then
  log "OK: Continue.dev config already present"
else
  log "Wiring Continue.dev to local Ollama (http://localhost:11434)..."
  as_user mkdir -p "$TARGET_HOME/.continue"
  sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
    "$REPO_ROOT/configs/vscodium/continue_config.yaml" \
    "$TARGET_HOME/.continue/config.yaml"
fi

# ---- Mission Center (Flathub) -------------------------------------------------------
if sudo flatpak info io.missioncenter.MissionCenter >/dev/null 2>&1; then
  log "OK: Mission Center already installed"
else
  log "Installing Mission Center (Task-Manager-style system monitor)..."
  sudo flatpak install -y --noninteractive flathub io.missioncenter.MissionCenter \
    || warn "Mission Center install failed"
fi

# ---- Chatbox (vendor .deb; NOT on Flathub anymore) ----------------------------------
# Latest version tag comes from the GitHub release of chatboxai/chatbox (e.g. v1.23.5).
# The deb's package name is xyz.chatboxapp.app.
chatbox_installed() {
  dpkg-query -W -f='${Status}' chatbox 2>/dev/null | grep -q 'install ok installed' \
    || dpkg-query -W -f='${Status}' xyz.chatboxapp.app 2>/dev/null | grep -q 'install ok installed'
}
if chatbox_installed; then
  log "OK: Chatbox already installed ($(dpkg-query -W -f='${Version}' xyz.chatboxapp.app 2>/dev/null))"
else
  log "Resolving latest Chatbox version..."
  chatbox_version="$(curl -fsSL --max-time 20 https://api.github.com/repos/chatboxai/chatbox/releases/latest \
    | jq -r '.tag_name // empty' | tr -d 'v')"
  if [ -z "$chatbox_version" ]; then
    warn "Could not resolve Chatbox version from GitHub — install it later from https://chatboxai.app"
  else
    deb_url="https://download.chatboxai.app/releases/Chatbox-${chatbox_version}-amd64.deb"
    log "Installing Chatbox ${chatbox_version} from vendor CDN..."
    tmp_deb="$(mktemp --suffix=.deb)"
    if curl -fsSL -o "$tmp_deb" "$deb_url"; then
      apt_install "$tmp_deb" || warn "Chatbox .deb install failed"
    else
      warn "Download failed: $deb_url"
    fi
    rm -f "$tmp_deb"
  fi
fi
log "Chatbox first-run hint: its wizard auto-detects the local Ollama on localhost:11434."

# ---- Permanent clipboard history (CopyQ) ----------------------------------------
# omarchy-style clipboard manager: tray-resident, history persisted to disk,
# searchable, images supported. Autostarts with the desktop session.
if dpkg-query -W -f='${Status}' copyq 2>/dev/null | grep -q 'install ok installed'; then
  log "OK: CopyQ already installed"
else
  log "Installing CopyQ (permanent clipboard history)..."
  apt_install copyq || warn "CopyQ install failed"
fi
if have copyq; then
  as_user mkdir -p "$TARGET_HOME/.config/copyq" "$TARGET_HOME/.config/autostart"
  if as_user test -f "$TARGET_HOME/.config/copyq/copyq.conf"; then
    log "OK: CopyQ config already present"
  else
    sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
      "$REPO_ROOT/configs/copyq/copyq.conf" \
      "$TARGET_HOME/.config/copyq/copyq.conf"
    log "OK: CopyQ preseeded (1000-entry permanent history, silent)"
  fi
  sudo install -m 644 "$REPO_ROOT/configs/autostart/copyq.desktop" \
    "$TARGET_HOME/.config/autostart/copyq.desktop"
  sudo chown "$TARGET_USER:$(id -gn "$TARGET_USER")" \
    "$TARGET_HOME/.config/autostart/copyq.desktop"
fi

sudo update-desktop-database >/dev/null 2>&1 || true
log "GUI applications complete."
