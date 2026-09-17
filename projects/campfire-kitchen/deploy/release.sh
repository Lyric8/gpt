#!/usr/bin/env bash
# campfire-kitchen 发布脚本（Hermes 维护）
#
# 用法：
#   ./deploy/release.sh --dry-run     # 只做目录/测试/构建/哈希闸门，不碰线上文件
#   ./deploy/release.sh               # 校验 → 构建 → 哈希闸门 → 发布 → reload → 实测
#
# 环境变量：
#   DEST      发布产物落点（默认 /var/www/campfire-kitchen/index.html）
#   BASE_URL  实测地址（默认 http://127.0.0.1/）
#
# 约定：仓库根目录不可部署；本脚本始终在 projects/campfire-kitchen 内运行。
set -euo pipefail

DRY_RUN=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$a" >&2; exit 2 ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
DEST="${DEST:-/var/www/campfire-kitchen/index.html}"
BASE_URL="${BASE_URL:-http://127.0.0.1/}"

step() { printf '\n=== %s ===\n' "$*"; }

step "1/5 项目完整性（$(pwd)）"
for f in data/recipes.json src/engine.mjs src/app.mjs src/styles.css tests/engine.test.mjs; do
  [ -f "$f" ] || { echo "缺少 $f：源码同步未完成，按仓库根 README 规则 6 停止发布。" >&2; exit 1; }
done

step "2/5 数据与引擎测试"
node tools/check_catalog.mjs
node --test tests/engine.test.mjs

step "3/5 构建"
python tools/build.py

step "4/5 哈希闸门"
built="$(sha256sum index.html | cut -d' ' -f1)"
want="$(grep -E '  index\.html$' SHA256SUMS.txt | cut -d' ' -f1 || true)"
echo "构建产物 sha256 = $built"
echo "SHA256SUMS 登记 = ${want:-（未登记）}"
if [ -n "$want" ] && [ "$built" != "$want" ]; then
  echo "哈希不一致：源码与登记值不同步，停止发布。" >&2
  echo "确认要发新版本时，先更新 SHA256SUMS.txt 中的 index.html 行。" >&2
  exit 1
fi

if [ "$DRY_RUN" = "1" ]; then
  echo
  echo "--dry-run：到此为止，未触碰线上文件。"
  exit 0
fi

step "5/5 发布与实测"
sudo mkdir -p "$(dirname "$DEST")"
sudo install -o root -g root -m 644 index.html "$DEST"
sudo systemctl reload caddy
sleep 1

served="$(mktemp)"
trap 'rm -f "$served"' EXIT
curl -sS -o "$served" "$BASE_URL"
served_hash="$(sha256sum "$served" | cut -d' ' -f1)"
[ "$served_hash" = "$built" ] || {
  echo "线上返回体与构建产物不一致：$served_hash" >&2; exit 1; }

curl -sS -I "$BASE_URL" | grep -qi '^X-Content-Type-Options: nosniff' || {
  echo "线上缺少 X-Content-Type-Options: nosniff" >&2; exit 1; }

code="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}docs/")"
[ "$code" = "404" ] || { echo "目录列表未关闭：/docs/ 返回 $code" >&2; exit 1; }

echo
echo "✅ 发布完成"
echo "   产物：$DEST"
echo "   实测：$BASE_URL 返回体哈希与构建产物一致（$built），nosniff 就位，目录列表已关闭"
