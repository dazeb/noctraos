#!/usr/bin/env bash
# r2-env.sh — rclone settings for the files.dazeb.dev / dl.noctraos.dev bucket. Sourced.
#
#   r2_env      sets RCLONE_CONFIG_R2_* so `rclone ... r2:$R2_BUCKET/...` works; never prints a secret.
#
# The credentials come from the environment (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT,
# R2_BUCKET) or, when those are unset, from ~/secrets/cloudflare-r2.env (override: R2_ENV_FILE).

r2_env() {
  if [ -z "${R2_ACCESS_KEY_ID:-}" ]; then
    local file="${R2_ENV_FILE:-$HOME/secrets/cloudflare-r2.env}"
    [ -r "$file" ] || { echo "no R2 credentials: set R2_* or provide $file" >&2; return 1; }
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
  : "${R2_SECRET_ACCESS_KEY:?}" "${R2_ENDPOINT:?}" "${R2_BUCKET:?}"
  export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
    RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
}
