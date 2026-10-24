#!/usr/bin/env bash
# renew-update-channels.sh — re-sign the update manifests so they do not expire (they last 30 days).
#
#   iso/renew-update-channels.sh
#
# For every flavour and channel that has a manifest (zorin: nightly, stable; kubuntu: kubuntu/nightly, kubuntu/stable) it runs
# `iso/publish-update.sh renew <channel> --flavour <flavour>`: same bundle, same serial, same rollout, a fresh signature and expiry,
# written to both stores and read back through the public hosts. Then it checks the PUBLIC manifest really expires at least
# RENEW_MIN_DAYS (25) from now. A client refuses an expired manifest, so a missed renewal turns "up to date" into "cannot check" for
# everyone. A channel nobody has published yet is skipped (nothing to renew), never reported as a failure. On any failure it exits
# non-zero and shows a desktop notification when it can.
# Runs weekly from a systemd user timer (iso/setup-update-renewal.sh) on the release workstation, the only place with the signing key.
# Environment: RENEW_CHANNELS ("nightly stable"), RENEW_FLAVOURS ("zorin kubuntu"), RENEW_CHECK_BASE, RENEW_MIN_DAYS (25), PUBLISH_UPDATE.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHANNELS="${RENEW_CHANNELS:-nightly stable}"
FLAVOURS="${RENEW_FLAVOURS:-zorin kubuntu}"
BASE="${RENEW_CHECK_BASE:-https://dl.noctraos.dev/updates}"
MIN_DAYS="${RENEW_MIN_DAYS:-25}"
log() { printf '=== %s %s\n' "$(date '+%F %H:%M')" "$*"; }

failed=()
for flavour in $FLAVOURS; do
  case "$flavour" in
    zorin) prefix="" ;;
    kubuntu) prefix="$flavour/" ;;
    *) failed+=("$flavour: unknown flavour"); continue ;;
  esac
  for ch in $CHANNELS; do
    label="$flavour $ch"
    case "$ch" in nightly|stable) ;; *) failed+=("$label: unknown channel"); continue ;; esac
    # Nothing published on this channel yet means nothing to renew; an unreachable or broken host still fails.
    if ! code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$BASE/${prefix}$ch/manifest.json" 2>/dev/null)"; then
      failed+=("$label: the public manifest answered ${code:-000} (transport failed)")
      continue
    fi
    case "$code" in
      200) ;;
      403|404) log "$label: no manifest published yet, nothing to renew"; continue ;;
      *) failed+=("$label: the public manifest answered $code"); continue ;;
    esac
    log "renewing the $label channel"
    if ! bash "${PUBLISH_UPDATE:-$HERE/publish-update.sh}" renew "$ch" --flavour "$flavour"; then
      failed+=("$label: the renewal itself failed")
      continue
    fi
    expires="$(curl -fsS --max-time 30 "$BASE/${prefix}$ch/manifest.json" 2>/dev/null | jq -r '.expires // empty' 2>/dev/null)"
    left=-1
    [ -n "$expires" ] && left=$(( ( $(date -u -d "${expires/T/ }" +%s 2>/dev/null || echo 0) - $(date -u +%s) ) / 86400 ))
    if [ "$left" -lt "$MIN_DAYS" ]; then
      failed+=("$label: the public manifest expires in $left days (wanted at least $MIN_DAYS)")
    else
      log "$label: the public manifest now expires in $left days"
    fi
  done
done

if [ ${#failed[@]} -gt 0 ]; then
  msg="$(printf '%s; ' "${failed[@]}")"
  log "FAILED: $msg"
  command -v notify-send >/dev/null 2>&1 && notify-send --urgency=critical --app-name=NoctraOS \
    "NoctraOS update manifests were not renewed" "$msg Clients refuse an expired manifest: run iso/publish-update.sh renew <channel>." || true
  exit 1
fi
log "all channels renewed"
