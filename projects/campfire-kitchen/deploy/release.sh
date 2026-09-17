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
  ./deploy/release.sh --deploy    # emergency/manual publish through the server installer

Normal production publishing is triggered only by a GitHub Release. --deploy is a break-glass fallback.
HELP
    [ -n "${1:-}" ] && exit 0 || exit 2
    ;;
  *) echo "unknown argument: $1" >&2; exit 2 ;;
esac
[ "$#" -eq 1 ] || { echo "only one argument is accepted" >&2; exit 2; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

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

step "4/4 break-glass deploy"
source_sha="$(git rev-parse HEAD)"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "cannot resolve a full git commit SHA" >&2; exit 1; }
label="manual-${package_version}-${source_sha}"
sudo /usr/local/sbin/campfire-kitchen-install-release deploy "$out1" "$label" "$built" "$source_sha"
echo "Manual fallback complete: $label"
