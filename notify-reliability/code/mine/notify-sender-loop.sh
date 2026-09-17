#!/usr/bin/env bash
# sender 常驻循环（systemd 服务，Restart=always）
#
# 落盘原则：**队列就是磁盘上的文件**，没有内存态。发成功才删文件；
# 所以进程随时被 kill / 崩溃，重启后剩下的条目照样在，一条不丢。
# 唯一窗口：发送成功与写 delivered.log 之间崩 → 重启后会重发一次（至多一次语义）。
#
# 崩溃要有人知道：非零退出或异常输出都写进 sender-crash.log，并留标记文件，
# 由 notify-sender.sh 在下一跳把报错原文作为一条通知发出去（崩溃必被上报）。
set -uo pipefail
SENDER=/home/ubuntu/.hermes/scripts/notify-sender.sh
CRASH=/home/ubuntu/.hermes/cache/sender-crash.log
MARK=/home/ubuntu/.hermes/cache/sender-crash-pending
SLEEP_S="${SENDER_LOOP_SLEEP:-20}"

while true; do
  out="$("$SENDER" 2>&1)"; ec=$?
  if [ "$ec" -ne 0 ] || printf '%s' "$out" | grep -qi "traceback"; then
    {
      printf '[%s] exit=%s\n' "$(date +%Y-%m-%dT%H:%M:%S%:z)" "$ec"
      printf '%s\n' "$out" | tail -25
      printf -- '---\n'
    } >> "$CRASH"
    : > "$MARK"
  fi
  sleep "$SLEEP_S"
done
