#!/usr/bin/env bash
# Module 02: mise — system-wide polyglot runtime management.
set -Eeuo pipefail
source "$REPO_ROOT/install/lib.sh"

if have mise; then
  log "OK: mise already installed ($(mise --version 2>/dev/null | head -n 1))"
else
  log "Installing mise to /usr/local/bin/mise (official installer)..."
  curl -fsSL https://mise.run | sudo MISE_INSTALL_PATH=/usr/local/bin/mise sh
fi
log "mise: $(sudo /usr/local/bin/mise --version 2>/dev/null | head -n 1)"

# Login shells (and the GNOME session itself) pick up /etc/profile.d.
PROFILE_FILE="/etc/profile.d/noctraos-mise.sh"
if [ -f "$PROFILE_FILE" ]; then
  log "OK: $PROFILE_FILE already present"
else
  log "Writing $PROFILE_FILE (mise activate for login shells)..."
  sudo tee "$PROFILE_FILE" >/dev/null <<'EOF'
# noctraos: activate mise for login shells and the desktop session
if command -v mise >/dev/null 2>&1; then
  case "$(basename "${SHELL:-bash}")" in
    zsh) eval "$(mise activate zsh)" 2>/dev/null || true ;;
    *)   eval "$(mise activate bash)" 2>/dev/null || true ;;
  esac
fi
EOF
fi

# Desktop terminals are interactive NON-login shells; they never read profile.d.
# /etc/bash.bashrc is sourced by every interactive bash on Ubuntu, so add a
# marked block there too.
if [ -f /etc/bash.bashrc ] && ! grep -q 'noctraos mise' /etc/bash.bashrc; then
  log "Adding mise activation to /etc/bash.bashrc (interactive non-login shells)..."
  sudo tee -a /etc/bash.bashrc >/dev/null <<'EOF'

# >>> noctraos mise >>> (managed block; do not edit)
if [ -n "${PS1:-}" ] && command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash)" 2>/dev/null || true
fi
# <<< noctraos mise <<<
EOF
fi

# System-wide baseline config (read by mise for every user).
if [ -f /etc/mise/config.toml ]; then
  log "OK: /etc/mise/config.toml already present"
else
  log "Installing /etc/mise/config.toml..."
  sudo mkdir -p /etc/mise
  sudo install -m 644 "$REPO_ROOT/configs/mise/config.toml" /etc/mise/config.toml
fi

# Per-user config, then bake in the runtimes immediately.
if as_user test -f "$TARGET_HOME/.config/mise/config.toml"; then
  log "OK: user mise config already present"
else
  log "Installing user mise config for $TARGET_USER..."
  as_user mkdir -p "$TARGET_HOME/.config/mise"
  sudo install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 644 \
    "$REPO_ROOT/configs/mise/config.toml" \
    "$TARGET_HOME/.config/mise/config.toml"
fi

log "Installing Node LTS (the coding-agent launchers and the Hermes build need it) and the terminal tools Herdr, Starship, lazygit, lazydocker..."
as_user mise install

# Existing users may have a pre-Herdr config. Keep their overrides and ensure
# the new tool still installs through mise's current Herdr registry entry.
if ! as_user mise where herdr >/dev/null 2>&1; then
  log "Installing Herdr through mise for the existing user config..."
  as_user mise use -g herdr@latest
fi
if ! as_user mise where starship >/dev/null 2>&1; then
  log "Installing Starship through mise for the existing user config..."
  as_user mise use -g starship@latest
fi
for tool in lazygit lazydocker; do
  if ! as_user mise where "$tool" >/dev/null 2>&1; then
    log "Installing $tool through mise for the existing user config..."
    as_user mise use -g "$tool@latest"
  fi
done

log "mise setup complete."
