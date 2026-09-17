#!/usr/bin/env bash
# Root-owned server-side installer for immutable Campfire Kitchen release artifacts.
# Installed by Hermes as /usr/local/sbin/campfire-kitchen-install-release.
set -euo pipefail

DEST="${CAMPFIRE_DEST:-/var/www/campfire-kitchen/index.html}"
STATE_ROOT="${CAMPFIRE_STATE_ROOT:-/var/lib/campfire-kitchen}"
BASE_URL="${CAMPFIRE_BASE_URL:-http://127.0.0.1/}"
RELEASES_DIR="$STATE_ROOT/releases"

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
sha256_file() { sha256sum -- "$1" | awk '{print $1}'; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "must run as root (normally through the dedicated sudo rule)"
}

validate_label() {
  local label="$1"
  [[ "$label" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
  [[ "$label" =~ ^manual-[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{7,40}$ ]] || \
    die "invalid release label: $label"
}

validate_sha256() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]] || die "invalid sha256: $1"
}

validate_source_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "invalid git source sha: $1"
}

prepare_state() {
  install -d -o root -g root -m 0755 "$STATE_ROOT" "$RELEASES_DIR" "$(dirname "$DEST")"
  touch "$STATE_ROOT/deployments.tsv"
  chmod 0644 "$STATE_ROOT/deployments.tsv"
}

validate_artifact_path() {
  local raw="$1" resolved
  [ ! -L "$raw" ] || die "artifact symlinks are not accepted"
  resolved="$(readlink -f -- "$raw")" || die "cannot resolve artifact path: $raw"
  [ -f "$resolved" ] || die "artifact is not a regular file: $resolved"
  case "$resolved" in
    /tmp/campfire-kitchen.*.html) ;;
    "$RELEASES_DIR"/*/index.html) ;;
    *) die "artifact must be an uploaded /tmp/campfire-kitchen.*.html or an immutable stored release" ;;
  esac
  printf '%s\n' "$resolved"
}

store_release() {
  local artifact="$1" label="$2" expected="$3" source_sha="$4"
  local release_dir="$RELEASES_DIR/$label" stored_hash tmp_dir

  if [ -e "$release_dir" ]; then
    [ -f "$release_dir/index.html" ] || die "release store is incomplete/corrupt: $release_dir"
    [ -f "$release_dir/SOURCE_SHA" ] || die "release store is missing SOURCE_SHA: $release_dir"
    stored_hash="$(sha256_file "$release_dir/index.html")"
    [ "$stored_hash" = "$expected" ] || die "release $label already exists with a different hash"
    [ "$(cat "$release_dir/SOURCE_SHA")" = "$source_sha" ] || die "release $label already exists with a different source commit"
    return 0
  fi

  tmp_dir="$(mktemp -d "$RELEASES_DIR/.${label}.XXXXXXXX")"
  trap 'rm -rf -- "$tmp_dir"' RETURN
  install -o root -g root -m 0644 "$artifact" "$tmp_dir/index.html"
  printf '%s  index.html\n' "$expected" > "$tmp_dir/SHA256SUMS"
  printf '%s\n' "$source_sha" > "$tmp_dir/SOURCE_SHA"
  cat > "$tmp_dir/manifest.json" <<JSON
{
  "version": "$label",
  "sha256": "$expected",
  "sourceSha": "$source_sha"
}
JSON
  chmod 0644 "$tmp_dir/SHA256SUMS" "$tmp_dir/SOURCE_SHA" "$tmp_dir/manifest.json"
  mv -- "$tmp_dir" "$release_dir"
  trap - RETURN
}

atomic_install() {
  local source="$1" tmp
  tmp="$(mktemp "$(dirname "$DEST")/.index.XXXXXXXX")"
  install -o root -g root -m 0644 "$source" "$tmp"
  mv -Tf -- "$tmp" "$DEST"
}

verify_live() {
  local expected="$1" body headers code served_hash
  body="$(mktemp "$STATE_ROOT/.served.XXXXXXXX")"
  headers="$(mktemp "$STATE_ROOT/.headers.XXXXXXXX")"
  trap 'rm -f -- "$body" "$headers"' RETURN

  if ! curl -fsS --retry 5 --retry-delay 1 --max-time 10 -o "$body" "$BASE_URL"; then
    printf 'live GET failed: %s\n' "$BASE_URL" >&2
    return 1
  fi
  served_hash="$(sha256_file "$body")"
  if [ "$served_hash" != "$expected" ]; then
    printf 'live sha256 mismatch: expected=%s actual=%s\n' "$expected" "$served_hash" >&2
    return 1
  fi
  if ! curl -fsS --retry 3 --retry-delay 1 --max-time 10 -I -o "$headers" "$BASE_URL"; then
    printf 'live HEAD failed: %s\n' "$BASE_URL" >&2
    return 1
  fi
  if ! tr -d '\r' < "$headers" | grep -qi '^X-Content-Type-Options:[[:space:]]*nosniff[[:space:]]*$'; then
    printf 'live response is missing X-Content-Type-Options: nosniff\n' >&2
    return 1
  fi
  code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "${BASE_URL%/}/docs/" || true)"
  if [ "$code" != "404" ]; then
    printf 'unexpected /docs/ status: %s (expected 404)\n' "$code" >&2
    return 1
  fi

  printf '%s\n' "$served_hash"
  trap - RETURN
  rm -f -- "$body" "$headers"
}

write_current() {
  local label="$1" expected="$2" source_sha="$3" action="$4" deployed_at="$5"
  local tmp
  tmp="$(mktemp "$STATE_ROOT/.current.XXXXXXXX")"
  cat > "$tmp" <<JSON
{
  "version": "$label",
  "sha256": "$expected",
  "sourceSha": "$source_sha",
  "action": "$action",
  "deployedAt": "$deployed_at"
}
JSON
  chmod 0644 "$tmp"
  mv -Tf -- "$tmp" "$STATE_ROOT/current.json"
}

switch_release() {
  local action="$1" label="$2" expected="$3" source_sha="$4"
  local release_file="$RELEASES_DIR/$label/index.html"
  local previous="" previous_hash="none" served_hash deployed_at had_previous=0

  [ -f "$release_file" ] || die "stored release not found: $label"
  [ "$(sha256_file "$release_file")" = "$expected" ] || die "stored release hash mismatch: $label"

  if [ -f "$DEST" ]; then
    previous="$(mktemp "$STATE_ROOT/.previous.XXXXXXXX.html")"
    cp -a -- "$DEST" "$previous"
    previous_hash="$(sha256_file "$previous")"
    had_previous=1
  fi

  atomic_install "$release_file"
  if ! served_hash="$(verify_live "$expected")"; then
    printf 'new release failed post-install verification; restoring previous live file\n' >&2
    if [ "$had_previous" -eq 1 ]; then
      atomic_install "$previous"
      if ! verify_live "$previous_hash" >/dev/null; then
        printf 'CRITICAL: rollback verification also failed; inspect server immediately\n' >&2
      fi
    else
      rm -f -- "$DEST"
    fi
    rm -f -- "$previous"
    die "deployment verification failed; previous release restored"
  fi

  deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_current "$label" "$expected" "$source_sha" "$action" "$deployed_at"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$deployed_at" "$action" "$label" "$expected" "$source_sha" "$previous_hash" >> "$STATE_ROOT/deployments.tsv"
  rm -f -- "$previous"

  say "campfire-kitchen $action OK"
  say "version=$label"
  say "artifact_sha256=$expected"
  say "served_sha256=$served_hash"
  say "previous_sha256=$previous_hash"
  say "source_sha=$source_sha"
}

cmd_deploy() {
  [ "$#" -eq 4 ] || die "usage: $0 deploy <artifact> <version> <sha256> <source-sha>"
  local artifact label="$2" expected="$3" source_sha="$4"
  validate_label "$label"
  validate_sha256 "$expected"
  validate_source_sha "$source_sha"
  artifact="$(validate_artifact_path "$1")"
  [ "$(sha256_file "$artifact")" = "$expected" ] || die "uploaded artifact hash does not match expected sha256"
  store_release "$artifact" "$label" "$expected" "$source_sha"
  case "$artifact" in /tmp/campfire-kitchen.*.html) rm -f -- "$artifact" ;; esac
  switch_release deploy "$label" "$expected" "$source_sha"
}

cmd_rollback() {
  [ "$#" -eq 1 ] || die "usage: $0 rollback <version>"
  local label="$1" expected source_sha release_dir="$RELEASES_DIR/$1"
  validate_label "$label"
  [ -f "$release_dir/index.html" ] || die "stored release not found: $label"
  expected="$(sha256_file "$release_dir/index.html")"
  source_sha="$(cat "$release_dir/SOURCE_SHA")"
  validate_source_sha "$source_sha"
  switch_release rollback "$label" "$expected" "$source_sha"
}

cmd_status() {
  if [ -f "$STATE_ROOT/current.json" ]; then
    cat "$STATE_ROOT/current.json"
  else
    say '{}'
  fi
  if [ -f "$DEST" ]; then
    say "live_sha256=$(sha256_file "$DEST")"
  else
    say "live_sha256=missing"
  fi
}

require_root
prepare_state
case "${1:-}" in
  deploy) shift; cmd_deploy "$@" ;;
  rollback) shift; cmd_rollback "$@" ;;
  status) shift; [ "$#" -eq 0 ] || die "usage: $0 status"; cmd_status ;;
  *) die "usage: $0 {deploy <artifact> <version> <sha256> <source-sha>|rollback <version>|status}" ;;
esac
