#!/usr/bin/env bash
# 把"即将发给老板的回复"登记进 outbox。
# 若那次发送被微信限流吞掉，补发任务（notify-retry.sh）会在下一跳重发。
#
# 用法：  notify-outbox.sh stage <文件>      # 文件内容 = 回复原文
# 说明：  登记只为「确认」用；发出去之后若日志里没有对应失败记录，登记会被自动清掉。
set -uo pipefail

QUEUE="${NOTIFY_QUEUE:-/home/ubuntu/.hermes/cache/notify-queue}"
OUT="$QUEUE/outbox"
mkdir -p "$OUT"

case "${1:-}" in
  stage)
    f="${2:?用法: notify-outbox.sh stage <文件>}"
    [ -r "$f" ] || { echo "读不到文件：$f" >&2; exit 2; }
    h="$(sha256sum "$f" | cut -c1-16)"
    ts="$(date +%Y%m%dT%H%M%S)"
    cp "$f" "$OUT/$ts-$h.txt"
    date +%Y-%m-%dT%H:%M:%S%:z > "$OUT/$ts-$h.staged"
    echo "已登记待确认发送：outbox/$ts-$h.txt"
    ;;
  list)
    ls -1 "$OUT"/*.txt 2>/dev/null | sed "s#$OUT/##" || echo "（无）"
    ;;
  *)
    echo "用法: notify-outbox.sh {stage <文件>|list}" >&2
    exit 2 ;;
esac
