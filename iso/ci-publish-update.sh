#!/usr/bin/env bash
# ci-publish-update.sh — what the GitLab update jobs run (.gitlab-ci.yml). A thin, checked front for iso/publish-update.sh.
#
#   iso/ci-publish-update.sh nightly [REF]      publish REF (default: the pipeline's tag) as the next update on the nightly channel
#   iso/ci-publish-update.sh promote PCT        move the update this pipeline built from nightly to the stable channel at PCT percent
#   iso/ci-publish-update.sh widen PCT          raise the stable channel's rollout to PCT percent (same update, same bundle)
#
# What it adds to publish-update.sh, because a job can be started by anyone who can push a protected tag:
#   * the commit must already be in the history of GitHub main (the public repository): an update ships merged, reviewed code;
#   * the notes come from the tag message (its first line); `Relogin: yes` and `Reboot: yes` lines in the message set the flags the
#     Updates page shows ("sign out and back in", "restart"). A tag without a message is described by its version;
#   * promote/widen refuse to act on anything but the update this pipeline built (a newer nightly or stable stays alone), and
#     never lower a rollout: a re-run of an old job cannot undo a wider rollout.
# A bundle is never replaced (publish-update.sh stops if one with that serial differs), so a retry of `nightly` is safe only
# because the serial moves on: retry the pipeline from a fresh tag when an update was published and was wrong.
# Environment (tests set these): UPDATE_MAIN_URL, UPDATE_PUBLIC_BASE, PUBLISH_UPDATE, UPDATE_REPO.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${UPDATE_REPO:-$(cd "$HERE/.." && pwd)}"
MAIN_URL="${UPDATE_MAIN_URL:-https://github.com/dazeb/noctraos.git}"
PUBLIC_BASE="${UPDATE_PUBLIC_BASE:-https://dl.noctraos.dev/updates}"
PUBLISH="${PUBLISH_UPDATE:-$HERE/publish-update.sh}"
die() { echo "ci-publish-update: $*" >&2; exit 1; }
log() { printf '=== %s\n' "$*"; }
g() { git -C "$REPO" "$@"; }

MODE="${1:-}"
ARG="${2:-}"

# The commit this pipeline is about: the tag it was started for, else the checked-out commit.
resolve_commit() {
  local ref="${1:-${CI_COMMIT_TAG:-HEAD}}"
  g rev-parse --verify --quiet "$ref^{commit}" || die "cannot find $ref in this checkout"
}

# Refuse a commit that is not part of GitHub main.
require_in_main() {
  local commit="$1"
  g fetch --quiet "$MAIN_URL" main || die "cannot read GitHub main from $MAIN_URL"
  g merge-base --is-ancestor "$commit" FETCH_HEAD \
    || die "${commit:0:7} is not in GitHub main: merge it first, then tag the merged commit"
}

# The channel's public manifest field, '' when the channel has no manifest yet.
public_field() {
  curl -fsS --connect-timeout 20 "$PUBLIC_BASE/$1/manifest.json" 2>/dev/null | jq -r "$2 // empty" 2>/dev/null || true
}

case "$MODE" in
  nightly)
    commit="$(resolve_commit "$ARG")"
    require_in_main "$commit"
    tag="${ARG:-${CI_COMMIT_TAG:-}}"
    notes="" body=""
    if [ -n "$tag" ] && [ "$(g for-each-ref --format='%(objecttype)' "refs/tags/$tag")" = tag ]; then
      notes="$(g for-each-ref --format='%(contents:subject)' "refs/tags/$tag")"
      body="$(g for-each-ref --format='%(contents:body)' "refs/tags/$tag")"
    fi
    [ -n "$notes" ] || notes="NoctraOS $(g show "$commit:VERSION" | tr -d '[:space:]')"
    flags=()
    grep -qiE '^relogin:[[:space:]]*(yes|true)[[:space:]]*$' <<<"$body" && flags+=(--relogin)
    grep -qiE '^reboot:[[:space:]]*(yes|true)[[:space:]]*$' <<<"$body" && flags+=(--reboot)
    log "publishing ${commit:0:7} on the nightly channel: $notes ${flags[*]:-}"
    bash "$PUBLISH" nightly --ref "$commit" --notes "$notes" "${flags[@]}" ;;

  promote|widen)
    [[ "$ARG" =~ ^([1-9][0-9]?|100)$ ]] || die "$MODE needs a rollout percentage, 1 to 100"
    commit="$(resolve_commit "")"
    from=nightly; [ "$MODE" = widen ] && from=stable
    have="$(public_field "$from" .commit)"
    [ -n "$have" ] || die "the $from channel has no update to $MODE"
    [ "$have" = "$commit" ] \
      || die "the $from channel now holds ${have:0:7}, not this pipeline's ${commit:0:7}: a newer update exists, $MODE that pipeline instead"
    current="$(public_field stable .rollout.percent)"
    if [ -n "$current" ] && [ "$(public_field stable .commit)" = "$commit" ] && [ "$current" -ge "$ARG" ]; then
      log "stable already serves this update to $current%: nothing to do"; exit 0
    fi
    log "stable: ${commit:0:7} to $ARG% (from $from)"
    bash "$PUBLISH" stable --from "$from" --rollout "$ARG" ;;

  *) die "usage: ci-publish-update.sh nightly [REF] | promote PCT | widen PCT" ;;
esac
