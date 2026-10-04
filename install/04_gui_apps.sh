#!/usr/bin/env bash
# Module 04: VS Code, Mission Center, and CopyQ; retire the previous app set.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

# Microsoft stable apt repository: https://code.visualstudio.com/docs/setup/linux
if [ ! -s /usr/share/keyrings/microsoft.gpg ]; then
  log "Installing Microsoft's apt signing key..."
  key_file="$(mktemp)"
  if ! curl -fsSL --max-time 60 https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor > "$key_file"; then
    rm -f "$key_file"
    die "Could not download Microsoft's signing key"
  fi
  sudo install -m 644 "$key_file" /usr/share/keyrings/microsoft.gpg
  rm -f "$key_file"
fi
if ! cmp -s "$REPO_ROOT/configs/vscode/vscode.sources" /etc/apt/sources.list.d/vscode.sources; then
  sudo install -m 644 "$REPO_ROOT/configs/vscode/vscode.sources" /etc/apt/sources.list.d/vscode.sources
  sudo apt-get update -y
fi
if dpkg-query -W -f='${Status}' code 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
  log "OK: VS Code already installed"
else
  log "Installing Microsoft VS Code..."
  # We manage the repository above; avoid the package's interactive repo prompt.
  echo 'code code/add-microsoft-repo boolean false' | sudo debconf-set-selections
  apt_install code
fi

# Install the replacement before removing old apps. Keep settings and chat data;
# no purge or autoremove, and remove only explicitly named installed packages.
retired=()
for package in codium chatbox xyz.chatboxapp.app foot; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -Fx 'install ok installed' >/dev/null; then
    retired+=("$package")
  fi
done
if [ "${#retired[@]}" -gt 0 ]; then
  log "Removing retired apps: ${retired[*]} (user data retained)"
  sudo DEBIAN_FRONTEND=noninteractive apt-get remove -y "${retired[@]}"
fi
# Remove only the repository file written by our earlier installer.
if [ -f /etc/apt/sources.list.d/vscodium.list ] \
  && grep -F 'https://download.vscodium.com/debs vscodium main' /etc/apt/sources.list.d/vscodium.list >/dev/null; then
  sudo rm -f /etc/apt/sources.list.d/vscodium.list
fi

# ---- extensions (per-extension idempotence) --------------------------------------
installed_exts="$(as_user code --list-extensions 2>/dev/null || true)"
while IFS= read -r ext; do
  case "$ext" in ''|'#'*) continue ;; esac
  if grep -qx "$ext" <<<"$installed_exts"; then
    log "OK: extension already installed: $ext"
  else
    log "Installing VS Code extension: $ext"
    as_user code --install-extension "$ext" || warn "Extension install failed: $ext"
  fi
done < "$REPO_ROOT/configs/vscode/extensions.list"

# ---- settings + Continue.dev → local Ollama ---------------------------------------
as_user mkdir -p "$TARGET_HOME/.config/Code/User"
if as_user test -f "$TARGET_HOME/.config/Code/User/settings.json"; then
  log "OK: VS Code settings already present"
else
  log "Installing VS Code settings..."
  sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
    "$REPO_ROOT/configs/vscode/settings.json" \
    "$TARGET_HOME/.config/Code/User/settings.json"
fi

if as_user test -f "$TARGET_HOME/.continue/config.yaml"; then
  log "OK: Continue.dev config already present"
else
  log "Wiring Continue.dev to local Ollama (http://localhost:11434)..."
  as_user mkdir -p "$TARGET_HOME/.continue"
  sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
    "$REPO_ROOT/configs/vscode/continue_config.yaml" \
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

# ---- No keyring prompt (autologin leaves the login keyring locked) --------------
# VS Code and Chromium would ask for a keyring password on first use; store their
# secrets without the keyring instead. Browsers installed later by the user are not
# covered (see AGENTS.md).
as_user python3 "$REPO_ROOT/scripts/seed-password-store.py" "$TARGET_HOME" \
  || warn "Could not set the keyring-free password store"

sudo update-desktop-database >/dev/null 2>&1 || true
log "GUI applications complete."
