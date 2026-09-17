#!/usr/bin/env bash
# Break-glass/manual release path. Normal production releases are GitHub Release-driven.
set -euo pipefail

MODE=""
case "${1:-}" in
  --dry-run) MODE="dry-run" ;;
  --deploy) MODE="deploy" ;;
  -h|--help|"")
    cat <<'HELP'
Usage:
  ./deploy/release.sh --dry-run   # validate + test + deterministic double build; no server changes
  ./deploy/release.sh --deploy    # emergency/manual publish through Hermes' restricted SSH channel

Normal production publishing is triggered only by a GitHub Release. --deploy is a break-glass fallback.
For --deploy, set DEPLOY_KEY_FILE and DEPLOY_KNOWN_HOSTS_FILE to local files.
HELP
    [ -n "${1:-}" ] && exit 0 || exit 2
    ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac
[ "$#" -eq 1 ] || { echo "only one argument is accepted" >&2; exit 2; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
DEPLOY_HOST="${DEPLOY_HOST:-124.223.114.109}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_USER="${DEPLOY_USER:-campfire-deploy}"
PUBLIC_URL="${PUBLIC_URL:-http://124.223.114.109/}"

step() { printf '\n=== %s ===\n' "$*"; }
cleanup_files=()
cleanup() { [ "${#cleanup_files[@]}" -eq 0 ] || rm -f -- "${cleanup_files[@]}"; }
trap cleanup EXIT

step "1/4 source completeness"
for f in data/recipes.json src/engine.mjs src/app.mjs src/styles.css tests/engine.test.mjs; do
  [ -f "$f" ] || { echo "missing $f; source sync is incomplete" >&2; exit 1; }
done

package_version="$(node -p "JSON.parse(require('fs').readFileSync('package.json','utf8')).version")"
data_version="$(node -p "JSON.parse(require('fs').readFileSync('data/recipes.json','utf8')).version")"
[[ "$package_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be stable SemVer X.Y.Z" >&2; exit 1; }
[ "$package_version" = "$data_version" ] || {
  echo "version mismatch: package.json=$package_version data/recipes.json=$data_version" >&2; exit 1; }

step "2/4 catalog + engine tests"
node tools/check_catalog.mjs
node --test tests/engine.test.mjs
node --check src/engine.mjs
node --check src/app.mjs

step "3/4 deterministic double build"
out1="$(mktemp /tmp/campfire-kitchen.manual.XXXXXXXX.html)"
out2="$(mktemp /tmp/campfire-kitchen.rebuild.XXXXXXXX.html)"
cleanup_files+=("$out1" "$out2")
python tools/build.py --output "$out1"
python tools/build.py --output "$out2"
cmp -s "$out1" "$out2" || { echo "non-deterministic build: two builds differ" >&2; exit 1; }
built="$(sha256sum "$out1" | awk '{print $1}')"
echo "artifact_sha256=$built"

if [ "$MODE" = "dry-run" ]; then
  echo "--dry-run complete; production was not touched."
  exit 0
fi

step "4/4 break-glass deploy through restricted SSH stdin"
: "${DEPLOY_KEY_FILE:?set DEPLOY_KEY_FILE to the deployment private-key file}"
: "${DEPLOY_KNOWN_HOSTS_FILE:?set DEPLOY_KNOWN_HOSTS_FILE to the pinned known_hosts file}"
[ -f "$DEPLOY_KEY_FILE" ] || { echo "DEPLOY_KEY_FILE does not exist" >&2; exit 1; }
[ -f "$DEPLOY_KNOWN_HOSTS_FILE" ] || { echo "DEPLOY_KNOWN_HOSTS_FILE does not exist" >&2; exit 1; }
ssh_opts=(-i "$DEPLOY_KEY_FILE" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$DEPLOY_KNOWN_HOSTS_FILE" -o ConnectTimeout=15 -p "$DEPLOY_PORT")
remote="${DEPLOY_USER}@${DEPLOY_HOST}"
deploy_output="$({
  printf 'version=1 tag=v%s sha256=%s\n' "$package_version" "$built"
  cat "$out1"
} | ssh "${ssh_opts[@]}" "$remote" deploy)"
printf '%s\n' "$deploy_output"
grep -Fq 'deploy-release: 完成' <<<"$deploy_output" || { echo "server did not report successful deployment" >&2; exit 1; }
grep -Fq "sha256=$built" <<<"$deploy_output" || { echo "server receipt hash mismatch" >&2; exit 1; }
served="$(mktemp /tmp/campfire-kitchen.served.XXXXXXXX.html)"
cleanup_files+=("$served")
curl -fsS --retry 5 --retry-delay 2 --max-time 20 -o "$served" "$PUBLIC_URL"
served_hash="$(sha256sum "$served" | awk '{print $1}')"
[ "$served_hash" = "$built" ] || { echo "public site hash mismatch: $served_hash" >&2; exit 1; }
echo "Manual fallback complete: tag=v${package_version} sha256=$built"
