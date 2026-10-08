#!/usr/bin/env bash
# r2-env.sh — rclone settings for the files.dazeb.dev / dl.noctraos.dev bucket. Sourced.
#
#   r2_env      sets RCLONE_CONFIG_R2_* so `rclone ... r2:$R2_BUCKET/...` works; never prints a secret.
#   store_env   picks the release store from RELEASE_STORE (r2, the default, or hetzner) and sets
#               STORE_REMOTE / STORE_BUCKET / STORE_PUBLIC_BASE for `rclone ... "$STORE_REMOTE:$STORE_BUCKET/..."`.
#
# hetzner = the noctraos-releases bucket on Hetzner Object Storage (Falkenstein, S3 API). Credentials come from
# AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or ~/secrets/noctraos-s3.env (override: NOCTRAOS_S3_ENV_FILE);
# NOCTRAOS_S3_ENDPOINT, NOCTRAOS_S3_BUCKET and RELEASE_PUBLIC_BASE override the defaults below.
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

store_env() {
  case "${RELEASE_STORE:-r2}" in
    r2)
      r2_env || return 1
      STORE_REMOTE=r2 STORE_BUCKET="$R2_BUCKET"
      STORE_PUBLIC_BASE="${RELEASE_PUBLIC_BASE:-https://dl.noctraos.dev}"
      ;;
    hetzner)
      local file="${NOCTRAOS_S3_ENV_FILE:-$HOME/secrets/noctraos-s3.env}"
      if [ -r "$file" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$file"
        set +a
      fi
      : "${AWS_ACCESS_KEY_ID:?no Hetzner S3 credentials: set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or provide $file}" "${AWS_SECRET_ACCESS_KEY:?}"
      export RCLONE_CONFIG_HZ_TYPE=s3 RCLONE_CONFIG_HZ_PROVIDER=Other \
        RCLONE_CONFIG_HZ_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" RCLONE_CONFIG_HZ_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
        RCLONE_CONFIG_HZ_ENDPOINT="${NOCTRAOS_S3_ENDPOINT:-https://fsn1.your-objectstorage.com}" \
        RCLONE_S3_CHUNK_SIZE="${RCLONE_S3_CHUNK_SIZE:-64M}"   # a 17 GB ISO stays well under the 10,000-part limit
      STORE_REMOTE=hz STORE_BUCKET="${NOCTRAOS_S3_BUCKET:-noctraos-releases}"
      STORE_PUBLIC_BASE="${RELEASE_PUBLIC_BASE:-https://$STORE_BUCKET.fsn1.your-objectstorage.com}"
      ;;
    *) echo "RELEASE_STORE must be r2 or hetzner, not '${RELEASE_STORE}'" >&2; return 1 ;;
  esac
  export STORE_REMOTE STORE_BUCKET STORE_PUBLIC_BASE
}
