#!/usr/bin/env bash
# setup-release-runner.sh — a GitLab runner for the release pipeline, on the workstation that has Docker,
# KVM, the secrets and the 2 TB build drive. No sudo: the runner is a systemd USER service.
#
#   iso/setup-release-runner.sh doctor     check what a release build needs on this machine (changes nothing)
#   iso/setup-release-runner.sh install    download gitlab-runner, register it with the project, start it
#   iso/setup-release-runner.sh status     runner state in GitLab and locally
#   iso/setup-release-runner.sh remove     stop it and delete the runner from GitLab
#
# Safety (a shell runner runs pipeline code as you, with your Docker, KVM and ~/secrets):
#   - it is a PROJECT runner for dazeb/noctraos only, locked, with a tag (`noctraos-release`) and no untagged jobs,
#   - it is ref-protected: it only takes jobs from protected refs, and `v*` tags are made protected here,
#   - one job at a time. Only people who can push a protected tag can start a release.
# The GitLab token comes from ~/secrets/gitlab.env (GITLAB_API_URL, GITLAB_API_KEY); nothing secret is printed.
# Environment: RUNNER_PROJECT (dazeb/noctraos), RUNNER_TAG (noctraos-release), RUNNER_BUILD_DIR
# (/run/media/dazeb/2tb/noctraos-release-ci), GITLAB_ENV (~/secrets/gitlab.env).
set -Eeuo pipefail

PROJECT="${RUNNER_PROJECT:-dazeb/noctraos}"
TAG="${RUNNER_TAG:-noctraos-release}"
BUILD_DIR="${RUNNER_BUILD_DIR:-/run/media/dazeb/2tb/noctraos-release-ci}"
BIN="$HOME/.local/bin/gitlab-runner"
CONF_DIR="$HOME/.config/gitlab-runner-noctraos"
UNIT="gitlab-runner-noctraos.service"
UNIT_FILE="$HOME/.config/systemd/user/$UNIT"
NAME="noctraos-release ($(hostname))"
say() { printf '%s\n' "$*"; }

api() {  # api METHOD PATH [curl args...] -> body on stdout, fails on HTTP errors
  local method="$1" path="$2"; shift 2
  curl -sSf -X "$method" -H "PRIVATE-TOKEN: $GITLAB_API_KEY" "$GITLAB_API_URL$path" "$@"
}
load_gitlab() {
  set -a
  # shellcheck disable=SC1090
  source "${GITLAB_ENV:-$HOME/secrets/gitlab.env}"
  set +a
  : "${GITLAB_API_URL:?}" "${GITLAB_API_KEY:?}"
  PID="$(api GET "/projects/${PROJECT//\//%2F}" | jq -r .id)"
}
runner_ids() { api GET "/projects/$PID/runners" | jq -r --arg d "$NAME" '.[]|select(.description==$d)|.id'; }

doctor() {
  local bad=0
  check() { if eval "$2" >/dev/null 2>&1; then say "ok   $1"; else say "MISSING  $1: $3"; bad=1; fi; }
  check "docker usable by $USER" "docker info" "add $USER to the docker group"
  check "/dev/kvm usable" "test -r /dev/kvm -a -w /dev/kvm" "needs KVM access (kvm group or an ACL)"
  check "qemu-system-x86_64, qemu-img" "command -v qemu-system-x86_64 && command -v qemu-img" "apt install qemu-system-x86 qemu-utils"
  check "OVMF firmware" "test -f /usr/share/OVMF/OVMF_CODE_4M.fd" "apt install ovmf"
  check "python3 venv (for torf)" "python3 -c 'import venv, ensurepip'" "apt install python3-venv"
  check "google-chrome (social cards; Pillow comes from a venv)" "command -v google-chrome" "the PR still opens without it, cards are not redrawn"
  check "rclone and R2 credentials" "command -v rclone && test -r \$HOME/secrets/cloudflare-r2.env" "$HOME/secrets/cloudflare-r2.env"
  check "gh logged in" "gh auth status" "gh auth login"
  check "ssh push to GitHub" "{ ssh -o BatchMode=yes -T git@github.com 2>&1 || true; } | grep 'successfully authenticated' >/dev/null" "an ssh key GitHub accepts"
  check "GitLab token" "test -r \${GITLAB_ENV:-\$HOME/secrets/gitlab.env}" "$HOME/secrets/gitlab.env"
  check "build drive" "test -d $(dirname "$BUILD_DIR") -a -w $(dirname "$BUILD_DIR")" "$(dirname "$BUILD_DIR") must exist and be writable"
  check "ext4 for the VM disk (/mnt/nvme1)" "test -w /mnt/nvme1" "VM_DIR must be on ext4"
  check "base Zorin ISO in $BUILD_DIR/in" "test -f $BUILD_DIR/in/Zorin-OS-18.1-Core-64-bit.iso" "install seeds it from an earlier build dir if it can find one"
  say "free: $(df -h --output=avail "$(dirname "$BUILD_DIR")" | tail -1 | tr -d ' ') on the build drive, $(df -h --output=avail /mnt/nvme1 | tail -1 | tr -d ' ') on /mnt/nvme1 (a release needs about 120 GB and 64 GB)"
  return "$bad"
}

install() {
  load_gitlab
  mkdir -p "$(dirname "$BIN")" "$CONF_DIR" "$BUILD_DIR/in" "$(dirname "$UNIT_FILE")"
  if [ ! -f "$BUILD_DIR/in/Zorin-OS-18.1-Core-64-bit.iso" ]; then
    seed="$(ls -t "$(dirname "$BUILD_DIR")"/noctraos-build*/in/Zorin-OS-18.1-Core-64-bit.iso 2>/dev/null | head -1 || true)"
    if [ -n "$seed" ]; then say "seeding the base ISO from $seed"; cp "$seed" "$BUILD_DIR/in/"; else say "NOTE: put Zorin-OS-18.1-Core-64-bit.iso in $BUILD_DIR/in/ before the first release"; fi
  fi
  if [ ! -x "$BIN" ]; then
    say "downloading gitlab-runner"
    base=https://gitlab-runner-downloads.s3.amazonaws.com/latest
    curl -sSfL "$base/binaries/gitlab-runner-linux-amd64" -o "$BIN.part"
    want="$(curl -sSf "$base/release.sha256" | awk '$2=="binaries/gitlab-runner-linux-amd64"{print $1}')"
    [ -n "$want" ] && [ "$(sha256sum "$BIN.part" | cut -d' ' -f1)" = "$want" ] || { rm -f "$BIN.part"; say "gitlab-runner download failed its checksum" >&2; exit 1; }
    chmod 755 "$BIN.part"; mv "$BIN.part" "$BIN"
  fi
  if [ -z "$(runner_ids)" ]; then
    say "creating the runner in GitLab (project $PROJECT, tag $TAG, protected refs only)"
    token="$(api POST /user/runners --data-urlencode runner_type=project_type --data-urlencode "project_id=$PID" \
      --data-urlencode "description=$NAME" --data-urlencode "tag_list=$TAG" --data-urlencode run_untagged=false \
      --data-urlencode locked=true --data-urlencode access_level=ref_protected --data-urlencode maximum_timeout=14400 | jq -r .token)"
    [ -n "$token" ] && [ "$token" != null ] || { say "GitLab did not return a runner token" >&2; exit 1; }
    : > "$CONF_DIR/config.toml"; chmod 600 "$CONF_DIR/config.toml"
    "$BIN" register --non-interactive --config "$CONF_DIR/config.toml" --url "${GITLAB_URL:-${GITLAB_API_URL%/api/v4}}" \
      --token "$token" --executor shell --name "$NAME" >/dev/null
    unset token
  else
    say "the runner already exists in GitLab; keeping it"
  fi
  sed -i 's/^concurrent = .*/concurrent = 1/' "$CONF_DIR/config.toml"

  say "protecting v* tags (only maintainers can push a release tag)"
  api GET "/projects/$PID/protected_tags" | jq -e '.[]|select(.name=="v*")' >/dev/null \
    || api POST "/projects/$PID/protected_tags" --data-urlencode 'name=v*' --data-urlencode create_access_level=40 >/dev/null

  cat > "$UNIT_FILE" <<UNITEOF
[Unit]
Description=GitLab runner for NoctraOS releases ($PROJECT, tag $TAG)
After=network-online.target docker.service

[Service]
ExecStart=$BIN run --config $CONF_DIR/config.toml --working-directory $BUILD_DIR/jobs
Restart=on-failure
RestartSec=10
# a release holds a VM and a 17 GB export: do not let a stop kill it half-way without the usual grace
TimeoutStopSec=120

[Install]
WantedBy=default.target
UNITEOF
  mkdir -p "$BUILD_DIR/jobs"
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT"
  loginctl enable-linger "$USER" 2>/dev/null || say "NOTE: could not enable linger; the runner then starts at login, not at boot"
  say "done. 'status' shows it online; push a tag vX.Y.Z to GitLab to release."
}

status() {
  load_gitlab
  for id in $(runner_ids); do api GET "/runners/$id" | jq -r '"GitLab runner \(.id): \(.status), tags \(.tag_list|join(",")), \(.access_level), locked=\(.locked), run_untagged=\(.run_untagged)"'; done
  [ -n "$(runner_ids)" ] || say "no runner registered for $PROJECT"
  systemctl --user is-active "$UNIT" 2>&1 | sed 's/^/service: /' || true
  api GET "/projects/$PID/protected_tags" | jq -r '"protected tags: " + ([.[].name]|join(", "))'
}

remove() {
  load_gitlab
  systemctl --user disable --now "$UNIT" 2>/dev/null || true
  for id in $(runner_ids); do api DELETE "/runners/$id" >/dev/null && say "deleted runner $id from GitLab"; done
  rm -f "$UNIT_FILE"; systemctl --user daemon-reload
  say "left in place: $BIN, $CONF_DIR, $BUILD_DIR (delete by hand if you want them gone)"
}

case "${1:-}" in
  doctor) doctor ;;
  install) install ;;
  status) status ;;
  remove) remove ;;
  *) sed -n '2,/^set -E/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//' ; exit 2 ;;
esac
