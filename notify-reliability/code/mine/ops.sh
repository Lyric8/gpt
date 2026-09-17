#!/usr/bin/env bash
# campfire/通讯 运维统一入口。**常用动作都走这里**，不要临场手写 bash。
#
# 纪律（老板明确要求）：
#   · 队列只装「自动化通知」（任务结果、告警、崩溃上报）
#   · **不给我的对话回复做保底** —— 那会造成同一条发两次；直接回复就是主路径
#   · 所有时间戳到秒、时区写 +08:00（禁止用地名表示时区）
#
# 用法：
#   ops.sh status                       一屏状态（双方队列/Release/线上/健康）
#   ops.sh site                         线上产物哈希 + HTTP + 字节数
#   ops.sh chat-new <slug> <body文件>    发新请求到 to-gpt（自动加时间头 + 走唯一推送通道）
#   ops.sh chat-reply <源消息路径> <body文件>  按协议用确定性名发回执
#   ops.sh status-row "<账本行>"         持资源租约 → CAS 追加 STATUS → 释放
#   ops.sh notify --file f | "文本"       给 sender 队列投一条通知（刻意使用，别用于回复）
#   ops.sh lease inspect|acquire|renew|release ...
#   ops.sh deploy-test [--dry-run]      部署通道端到端自测（临时钥匙，自清理）
#   ops.sh pending                      两边待办一眼看（to-hermes / to-gpt）
#   ops.sh one-tab                     只留一个浏览器标签（关掉多余）
#   ops.sh check-ui                    检查浏览器交互是否合规（禁 JS/合成按键）
#   ops.sh kit [--list]                 拟人化浏览器资料包：重新生成 / 列出已有
set -uo pipefail

S=/home/ubuntu/.hermes/scripts
REPO=/home/ubuntu/src/gpt
CRED=/home/ubuntu/.git-credentials
API=https://api.github.com/repos/Lyric8/gpt
TS() { date +%Y-%m-%dT%H:%M:%S%:z; }
TOKEN() { sed -nE 's#https://[^:]+:([^@]+)@github.com#\1#p' "$CRED" | head -1; }
api() { curl -s --max-time 25 -H "Authorization: Bearer $(TOKEN)" "$@"; }

cmd="${1:-}"; shift || true

case "$cmd" in

status)
  echo "── 时间 $(TS)"
  api "$API/commits/chat" | python3 -c "
import sys,json,datetime
d=json.load(sys.stdin); t=d['commit']['author']['date']
dt=datetime.datetime.strptime(t,'%Y-%m-%dT%H:%M:%SZ')+datetime.timedelta(hours=8)
print('chat HEAD  %s  %s  %s' % (d['sha'][:8], dt.strftime('%H:%M:%S'), d['commit']['message'].splitlines()[0][:46]))
"
  "$S/chat-queue.sh" list 2>/dev/null | tail -n +2 | awk '{print "  收件 " $0}'
  api "$API/releases" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Release 数 %d %s' % (len(d), ('(最近: '+d[0]['tag_name']+')') if d else '(还没有)'))
"
  H=$(sha256sum /var/www/campfire-kitchen/index.html | cut -d' ' -f1)
  echo "线上      ${H:0:16}  $(curl -s -o /dev/null -w '%{http_code} %{size_download}B' --max-time 15 https://furrypant.com/)"
  python3 -c "
import json
d=json.load(open('/home/ubuntu/.hermes/cron/jobs.json'))
js=d if isinstance(d,list) else d.get('jobs',d)
if isinstance(js,dict): js=list(js.values())
for j in js:
    print('任务      %-14s %-18s %s  %s' % (j.get('id'), (j.get('name') or '')[:16], (j.get('last_run_at') or '')[:19].replace('T',' '), j.get('last_status')))
"
  echo "评估层    $(cat /home/ubuntu/.hermes/cache/campfire-eval-heartbeat 2>/dev/null)"
  echo "发送者    [$(systemctl is-active campfire-sender.service)] $(cat /home/ubuntu/.hermes/cache/notify-sender-heartbeat 2>/dev/null)"
  echo "队列      $(ls /home/ubuntu/.hermes/cache/notify-queue/*.txt 2>/dev/null | wc -l) 条待发"
  ;;

site)
  H=$(sha256sum /var/www/campfire-kitchen/index.html | cut -d' ' -f1)
  echo "sha256   $H"
  echo "字节     $(wc -c </var/www/campfire-kitchen/index.html)"
  echo "HTTP     $(curl -s -o /dev/null -w '%{http_code} %{time_total}s' --max-time 20 https://furrypant.com/)"
  ;;

chat-new)
  slug="${1:?用法: ops.sh chat-new <slug> <body文件>}"; body="${2:?要传正文文件}"
  [ -r "$body" ] || { echo "读不到 $body" >&2; exit 2; }
  f="$REPO/chat/to-gpt/$(date +%Y-%m-%dT%H%M%S%z)-$slug.md"
  { printf '时间：%s　作者：Hermes\n\n' "$(TS)"; cat "$body"; } > "$f"
  echo "  已写入 ${f#$REPO/}"
  head -1 "$f" | sed 's/^/  /'
  "$S/chat-push.sh" "chat(to-gpt): $slug" | sed 's/^/  /'
  ;;

chat-reply)
  src="${1:?用法: ops.sh chat-reply <源消息路径> <body文件>}"; body="${2:?要传正文文件}"
  p="${src#chat/}"; p="${p#/}"
  id=$("$S/chat-queue.sh" claim "$p" 2>/dev/null | sed -n 's/.*\(GRANTED\|TAKEOVER\)  *//p')
  [ -n "$id" ] || { echo "拿不到该消息的 message_id（先看 ops.sh pending）" >&2; exit 1; }
  f="$REPO/chat/to-gpt/$id.md"
  { printf '时间：%s　作者：Hermes\n' "$(TS)"; printf '对应消息：`chat/%s`\n\n' "$p"; cat "$body"; } > "$f"
  echo "  回执（确定性名）${f#$REPO/}"
  "$S/chat-push.sh" "chat(to-gpt): 回执 $id" | sed 's/^/  /'
  ;;

status-row)
  row="${1:?用法: ops.sh status-row \"<账本行>\"}"
  # 纪律：**不要**在这里自己先 acquire resource:chat/STATUS.md ——
  # chat-queue.sh status-append 内部已按 RESOURCE_LEASE_PROTOCOL 先持租约、再 blob SHA CAS 追加、写完即释放；
  # 外面再拿一次会让内层 acquire 直接 BUSY（该客户端不重入），账本反而写不进去。
  # 2026-09-17T18:47+08:00 实测踩到过：外层拿到 fence=18，内层报 BUSY，行没写进去。
  out=$("$S/chat-queue.sh" status-append "$row" 2>&1); ec=$?
  printf '%s\n' "$out" | sed 's/^/  /'
  case "$ec" in
    0)  echo "  账本行已追加（资源租约 + blob SHA CAS 均由 status-append 负责）" ;;
    10) echo "  被别人持有（BUSY）→ 排队，本轮不改账本"; exit 10 ;;
    *)  echo "  追加失败（rc=$ec：20=故障 / 4=CAS 连续冲突）→ 不动账本，交回调用方重试"; exit 20 ;;
  esac
  ;;

notify)
  dry=no
  if [ "${1:-}" = "--dry-run" ]; then dry=yes; shift; fi
  if [ "${1:-}" = "--file" ]; then src="$2"; elif [ -n "${1:-}" ]; then printf '%s\n' "$1" > /tmp/ops-notify.txt; src=/tmp/ops-notify.txt; else echo "用法: ops.sh notify [--dry-run] --file f | \"文本\"" >&2; exit 2; fi
  [ "$dry" = "yes" ] && { echo "  dry-run：会投递 → $(head -c 80 "$src")"; exit 0; }
  # 刻意通知直接进队列（必发）；outbox 只用于「对话回复兜底」（仅失败才补发）
  Q=/home/ubuntu/.hermes/cache/notify-queue; mkdir -p "$Q"
  h=$(sha256sum "$src" | cut -c1-16); f="$Q/$(date +%Y%m%dT%H%M%S)-$h.txt"
  cp "$src" "$f"; echo "  已入队 $(basename "$f")（sender 下一轮发送，自动拆片）"
  ;;

lease)  python3 "$S/chat-resource-lease.py" "$@"; ;;

pending)
  echo "── to-hermes（我的待办）"
  "$S/chat-queue.sh" list 2>/dev/null | tail -n +2 | grep -c "completed=no" | sed 's/^/  未完成: /'
  echo "── to-gpt（它的待办）"
  api "$API/contents/chat/to-gpt?ref=chat" | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print('  取不到'); raise SystemExit
n=len([e for e in d if e['name'].endswith('.md')])
print('  消息 %d 条（其中历史 baseline 9 条）' % n)
"
  ;;

browser)  "$S/chrome-proxy.sh" "$@" ;;   # 受控浏览器：强制全程走代理（start|stop|check）

deploy-test)
  dry=no; [ "${1:-}" = "--dry-run" ] && dry=yes
  AK=/var/lib/campfire-deploy/.ssh/authorized_keys
  TMP=/tmp/ops-deploytest_key
  LIVE=/var/www/campfire-kitchen/index.html
  H=$(sha256sum "$LIVE" | cut -d' ' -f1)
  MAIN=$(api "$API/commits/main" | python3 -c "import sys,json;print(json.load(sys.stdin)['sha'])")
  LABEL="manual-2.0.0-${MAIN:0:7}"
  echo "  计划：临时钥匙 → status → deploy(label=$LABEL, source=${MAIN:0:12}, sha=${H:0:12}) → 校验 → 移除钥匙并复原"
  [ "$dry" = "yes" ] && exit 0
  ssh-keygen -q -t ed25519 -N '' -f "$TMP" -C ops-selftest >/dev/null 2>&1
  sudo bash -c "cat >> $AK" <<EOF
restrict,command="/usr/local/bin/campfire-ssh-entry" $(cat "$TMP.pub")
EOF
  sudo bash -c "chown campfire-deploy:campfire-deploy $AK; chmod 600 $AK"
  SSH="ssh -i $TMP -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes"
  echo "  --- status ---"
  echo "request=status" | $SSH campfire-deploy@127.0.0.1 status 2>/dev/null | grep -E 'live_sha256|"action"' | sed 's/^/    /'
  echo "  --- deploy ---"
  { printf 'request=deploy label=%s sha256=%s source=%s\n' "$LABEL" "$H" "$MAIN"; cat "$LIVE"; } \
    | $SSH campfire-deploy@127.0.0.1 deploy 2>&1 | grep -v "Warning: Permanently" | tail -7 | sed 's/^/    /'
  NOW=$(sha256sum "$LIVE" | cut -d' ' -f1)
  [ "$NOW" = "$H" ] && echo "  线上未变 ✅" || echo "  ⚠️ 线上变了：$NOW"
  sudo bash -c "head -1 $AK > /tmp/ak.clean && mv /tmp/ak.clean $AK && chown campfire-deploy:campfire-deploy $AK && chmod 600 $AK"
  rm -f "$TMP" "$TMP.pub"
  echo "  钥匙复原：行数 $(sudo bash -c "wc -l < $AK") 指纹 $(sudo bash -c "ssh-keygen -lf $AK" | cut -d' ' -f2)"
  ;;

one-tab)
  python3 -c "
import sys; sys.path.insert(0,'/home/ubuntu/.hermes/scripts')
from cdpmini import ensure_single_tab
r = ensure_single_tab()
print('  保留:', (r or {}).get('url','?')[:70])
print('  已关掉:', (r or {}).get('closed', 0), '个多余标签')"
  ;;

check-ui)
  # 硬规矩：浏览器交互只允许真点击/拖拽/文本输入
  bash "$S/check-forbidden-ops.sh" "${1:-}"
  ;;

kit)
  # 拟人化浏览器资料包：重新生成（从线上脚本现取）或列出已有
  bash "$S/make-browser-kit.sh" "${1:-}"
  ;;

slots)
  # GPT 侧 10 个监听任务（:00~:54）的交接次数统计；满 20 自动轮换
  python3 "$S/slot-stats.py" --table
  ;;

*)
  sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 2 ;;
esac
