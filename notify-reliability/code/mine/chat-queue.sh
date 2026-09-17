#!/usr/bin/env bash
# Hermes 侧：chat 队列协议 v3 的接入工具（claim / complete / status-append / list）
#
# 协议权威版本：chat/LEASE_PROTOCOL.md（作者 ChatGPT，方向 to-hermes 由本工具充当 worker）
# 本工具只做协议要求的那几件原子事，不含业务判断 —— 业务判断仍由 Hermes 的会话层做。
#
# v3 命名（2026-09-18 落地）：文件名 = 精确时间戳 + 主旨，流转身份写正文（message_id /
# message_blob_sha）；**claim 是例外**：它的时间戳取 source message 的稳定时间，
# 这样所有竞争者推出同一个 create-file 竞争点（详见 source_ts()）。
#
# 用法：
#   chat-queue.sh list                                  列出候选（含 message_id 与是否已领）
#   chat-queue.sh claim    <message_path>               原子领租约（create-file 竞争裁决；成功即自动挂续租 watchdog）
#   chat-queue.sh renew    <message_path>               续租（nonce 校验 + CAS；租约 60 分钟）
#   chat-queue.sh lease-state <message_path>            本地租约状态：held | lost | none
#   chat-queue.sh path-of  claim|completed <message_path>  只读诊断：打印该消息的标记路径
#   chat-queue.sh complete <message_path> <status> <evidence>
#                                                      写 completed marker（幂等；已存在则跳过）
#   chat-queue.sh status-append "<账本行>"              持 resource:chat/STATUS.md lease + blob SHA CAS 追加账本行
#   chat-queue.sh resource-lease <op> ...               转交共享资源 lease 客户端（chat-resource-lease.py，协议 chat/RESOURCE_LEASE_PROTOCOL.md）
#
# status 取值：resolved | rejected | non-request
#
# 续租节律（协议裁决 2026-09-17T17:38:41+08:00）：lease 60 分钟，45 分钟是**硬安全边界**，
# 落地实现为 40 分钟自动续租 watchdog（arm_lease / __watchdog）。测试钩子环境变量：
#   CHAT_QUEUE_RENEW_AFTER_SEC  默认 2400（40 分钟）
#   CHAT_QUEUE_WATCHDOG_TICK_SEC 默认 30
#   CHAT_QUEUE_WATCH_PID        默认 $PPID（watchdog 盯的"任务进程"；它退出即停续租）
#   CHAT_QUEUE_NO_WATCHDOG=1    只领租约、不挂 watchdog
set -uo pipefail

# ── 文件名硬上限护栏（2026-09-17 加）────────────────────────────
# 现象：回执名"每轮再挂一个 40 字符 sha"会累加到 278 字符 → 本机 git 无法 checkout（File name too long）。
# 处理：超过 200 字符时**拒绝用长名**，改用短名（基名 + 父 blob sha 前 12 位），完整链写进正文。
MAXNAME=200
short_name() {   # $1=长名  输出=安全名
  local n="$1"
  if [ "${#n}" -le "$MAXNAME" ]; then printf '%s' "$n"; return; fi
  local base="${n%%--*}" tail_sha="${n##*--}"
  tail_sha="${tail_sha%.json}"; tail_sha="${tail_sha%.md}"
  printf '%s--%s.%s' "$base" "${tail_sha:0:12}" "${n##*.}"
}


REPO="/home/ubuntu/src/gpt"
BRANCH="chat"
API="https://api.github.com/repos/Lyric8/gpt/contents"
OWNER_NAME="hermes-poller"
LEASE_MINUTES=60
PROCESSED_LIST="/home/ubuntu/.hermes/cache/campfire-inbox-processed.txt"
NONCE_DIR="/home/ubuntu/.hermes/cache/locks/nonces"
RENEW_AFTER_SEC="${CHAT_QUEUE_RENEW_AFTER_SEC:-2400}"       # 40 分钟
WATCHDOG_TICK_SEC="${CHAT_QUEUE_WATCHDOG_TICK_SEC:-30}"
WATCHDOG_MAX_SEC="${CHAT_QUEUE_WATCHDOG_MAX_SEC:-21600}"    # 6 小时自保上限
SELF="$(readlink -f "$0")"
CRED="/home/ubuntu/.git-credentials"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$NONCE_DIR"

TOKEN="$(sed -nE 's#https://[^:]+:([^@]+)@github.com#\1#p' "$CRED" | head -1)"
[ -n "$TOKEN" ] || { echo "chat-queue: 找不到凭据" >&2; exit 5; }

# claim_nonce 生成器：协议裁决（2026-09-17T17:38:41+08:00）定稿要求 opaque 高熵唯一 token，
# 纯时间戳不合格、`$RANDOM` 随机空间不够。首选 UUIDv4，退路 128-bit 随机；全失败就拒绝领租约。
new_nonce() {
  local u=""
  if [ -r /proc/sys/kernel/random/uuid ]; then
    u="$(cat /proc/sys/kernel/random/uuid)"
  elif command -v uuidgen >/dev/null 2>&1; then
    u="$(uuidgen | tr 'A-Z' 'a-z')"
  elif command -v openssl >/dev/null 2>&1; then
    u="$(openssl rand -hex 16)"
  fi
  case "$u" in
    *[!0-9a-f-]*|"") u="" ;;
  esac
  [ -n "$u" ] || u="$(python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null)"
  [ -n "$u" ] || { echo "chat-queue: 生成 claim_nonce 失败（无 uuid 源）" >&2; exit 5; }
  printf '%s' "$u"
}

# 盯谁算"任务还活着"：从调用者的父进程向上走，跳过一层层短命的 shell 包装
# （Hermes 的终端调用是「每次一个 bash」，它退出不等于任务结束），停在第一个非 shell 进程上
# —— 那通常是会话进程本身。可用 CHAT_QUEUE_WATCH_PID 显式覆盖。
watch_anchor() {
  local pid="${CHAT_QUEUE_WATCH_PID:-$PPID}" comm
  while [ "${pid:-0}" -gt 1 ] 2>/dev/null; do
    comm="$(ps -o comm= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "$comm" ] || break
    case "$comm" in
      bash|sh|dash|zsh|ksh|timeout|env|nohup|setsid|xargs) pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')";;
      *) break ;;
    esac
  done
  [ -n "${pid:-}" ] && [ "$pid" -gt 1 ] 2>/dev/null && printf '%s' "$pid" || printf '%s' "$PPID"
}

# 拿到租约后：记录本地元数据，并挂 40 分钟续租 watchdog。
# watchdog 只盯两件事：本地凭据还在不在、任务进程还活着不活着；任务结束（complete 清凭据）即自行退出。
arm_lease() { # $1=id $2=message_path $3=nonce
  local id="$1" p="$2" nonce="$3" ep wpid
  ep="$(date +%s)"; wpid="$(watch_anchor)"
  {
    echo "claimed_epoch=$ep"
    echo "claimed_at=$(now)"
    echo "message_path=$p"
    echo "nonce=$nonce"
    echo "watch_pid=$wpid"
    echo "renew_after_sec=$RENEW_AFTER_SEC"
  } > "$NONCE_DIR/$id.meta"
  [ "${CHAT_QUEUE_NO_WATCHDOG:-0}" = "1" ] && return 0
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$SELF" __watchdog "$id" "$p" "$ep" "$wpid" >> "$NONCE_DIR/$id.watch.log" 2>&1 &
  else
    nohup "$SELF" __watchdog "$id" "$p" "$ep" "$wpid" >> "$NONCE_DIR/$id.watch.log" 2>&1 &
  fi
  echo $! > "$NONCE_DIR/$id.watch.pid"
}

api() { # api METHOD URL [json]
  local m="$1" u="$2" d="${3:-}"
  if [ -n "$d" ]; then
    curl -s --max-time 30 -X "$m" -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.github+json" -d "$d" "$u"
  else
    curl -s --max-time 30 -X "$m" -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.github+json" "$u"
  fi
}

# 取某路径在远端 chat 分支上的 blob sha（不存在则空）
blob_sha() {
  api GET "$API/$1?ref=$BRANCH" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
except Exception: print(''); raise SystemExit
print(d.get('sha','') if isinstance(d,dict) else '')
"
}

message_id() { # $1 = chat/to-hermes/xxx.md
  local f="${1#chat/to-hermes/}"; f="${f%.md}"
  local s; s="$(blob_sha "$1")"
  [ -n "$s" ] && printf '%s--%s' "$f" "$s"
}

json_get() { python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print(''); raise SystemExit
for k in sys.argv[1:]:
    d=d.get(k,'') if isinstance(d,dict) else ''
print(d)
" "$@"; }

put_file() { # put_file <path> <content> [sha]  → 输出 ok|conflict
  local p="$1" c="$2" sha="${3:-}"
  local b64 body
  # 注意：这里用 printf '%s\n'（不是 '%s'）。调用方常用 "$(cat 文件)" 传内容，而命令替换会把
  # 结尾换行全部吃掉；若这里不再补回，写出的文件就不以换行结尾，下一次追加会把新行**粘到上一行行尾**
  # （2026-09-17 实测：STATUS.md 两条账本行粘成一行）。
  b64="$(printf '%s\n' "$c" | base64 -w0)"
  if [ -n "$sha" ]; then
    body="$(python3 -c "
import json,sys
print(json.dumps({'message':sys.argv[1],'content':sys.argv[2],'sha':sys.argv[3],'branch':sys.argv[4]}))
" "chat($OWNER_NAME): ${p##*/}" "$b64" "$sha" "$BRANCH")"
  else
    body="$(python3 -c "
import json,sys
print(json.dumps({'message':sys.argv[1],'content':sys.argv[2],'branch':sys.argv[3]}))
" "chat($OWNER_NAME): ${p##*/}" "$b64" "$BRANCH")"
  fi
  api PUT "$API/$p" "$body" > "$TMP/put.json"
  python3 - "$TMP/put.json" <<'PY'
import sys,json
try: d=json.load(open(sys.argv[1]))
except Exception: print('error'); raise SystemExit
if isinstance(d,dict) and d.get('content') and d['content'].get('sha'):
    print('ok')
else:
    msg=str(d.get('message','')) if isinstance(d,dict) else ''
    st=str(d.get('status','')) if isinstance(d,dict) else ''
    # 注意：GitHub 错误正文里的 "status" 是**字符串**（"409"/"422"），必须按字符串比较；
    # 并发 create 竞态还可能返回 409 且正文不含 "already exists"/"does not match"
    hit = st in ('409','422') or 'already exists' in msg or 'does not match' in msg or 'wasn' in msg or 'expected' in msg
    print('conflict' if hit else 'error')
PY
}

now_plus_min() { date -d "+${1} minutes" +%Y-%m-%dT%H:%M:%S%:z; }
now() { date +%Y-%m-%dT%H:%M:%S%:z; }

# ── 文件名规矩（老板 2026-09-17 强制）────────────────────────────────
# 文件名 = 极其精确的时间戳 + 主旨；**不许**在名字上挂 message_id / sha 链；
# 转运信息（source_path / message_id）写在正文里。理由：sha 链每回一轮加一层，
# 实测已到 278 字符 → 超过文件系统 255 上限 → 本机 git 无法 checkout（File name too long）。
ts_file() { date +%Y-%m-%dT%H%M%S%z; }   # 例 2026-09-17T235012+0800（无冒号，Windows 检出也安全）
topic_of() { # $1=消息路径 → 主旨（剥掉 sha 链、扩展名、日期/时间前缀）
  local b; b="$(basename -- "$1")"; b="${b%%--*}"; b="${b%.md}"; b="${b%.json}"
  b="$(printf '%s' "$b" | sed -E 's/^(20[0-9]{2})-?[0-9]{2}-?[0-9]{2}[-_]?//; s/^T?[0-9]{6}\+?[0-9]{4}[-_]?//')"
  printf '%s' "${b:0:56}" | tr -c 'A-Za-z0-9._-' '-'
}

# ── v3：claim 的稳定竞争点（协议 chat/LEASE_PROTOCOL.md v3「claim 的关键例外」）──
# claim 文件名的时间戳必须取 **source message 自身的稳定时间**，不能取本次 claim 的当前时间：
# 否则两个竞争者各自生成不同路径，create-file 这个原子裁决点就不存在了（可能双 owner）。
# 优先级：① source 文件名已是 YYYY-MM-DDTHHMMSS+0800-… → 用它；
#        ② 历史文件名没有精确时间戳 → 读 immutable 正文首个 `时间：`（作者写的创建时间，稳定）；
#        ③ 都拿不到 → fail closed（return 1），调用方不创建 claim 路径。
source_ts() { # $1=chat/to-hermes/xxx.md → 2026-09-17T235620+0800
  local ts
  ts="$(printf '%s' "$(basename -- "$1")" | sed -nE 's/^(20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{6}\+0800).*/\1/p')"
  if [ -z "$ts" ]; then
    ts="$(api GET "$API/$1?ref=$BRANCH" | json_get content | base64 -d 2>/dev/null \
      | sed -nE 's/^时间：(20[0-9]{2}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\+08:00.*/\1T\2\3\4+0800/p' \
      | head -1)"
  fi
  [ -n "$ts" ] || return 1
  printf '%s' "$ts"
}

marker_path() { # $1=方向(to-hermes/to-gpt)  $2=state(claim/completed)  $3=源消息路径  [$4=claim 的 source_ts]
  local d; d="$2"; [ "$d" = "claim" ] && d="claims"
  printf 'chat/%s/%s/%s-%s-%s.json' "$d" "$1" "${4:-$(ts_file)}" "$2" "$(topic_of "$3")"
}
local_key() { # 本地凭据键（短、确定）：主旨 + 源文件 sha 前 12 位
  local s; s="$(blob_sha "$1")"
  printf '%s-%s' "$(topic_of "$1")" "${s:0:12}"
}

cmd="${1:-}"; shift || true

case "$cmd" in
list)
  echo "  方向：to-hermes（我的收件箱）　远端分支：$BRANCH"
  ls_now="$(api GET "$API/chat/to-hermes?ref=$BRANCH" | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: raise SystemExit
for e in d: print(e['path'])
")"
  [ -n "$ls_now" ] || { echo "  取不到目录（网络/凭据）"; exit 6; }
  IDX="$TMP/marker-index.tsv"
  /home/ubuntu/.hermes/scripts/chat-marker-index.py to-hermes > "$IDX" 2>/dev/null || : > "$IDX"
  while read -r p; do
    [ "$p" = "chat/to-hermes/README.md" ] && continue
    sha="$(api GET "$API/$p?ref=$BRANCH" | json_get sha)"
    cl="$(awk -F'\t' -v s="$sha" '$1==s && $2=="claim"{print "yes"; exit}' "$IDX")"
    comp="$(awk -F'\t' -v s="$sha" '$1==s && $2=="completed"{print "yes"; exit}' "$IDX")"
    printf '  %-58s claim=%-4s completed=%-4s\n' "$(basename "$p")" "${cl:-no}" "${comp:-no}"
  done <<< "$ls_now"
  ;;

claim)
  p="${1:?要传 message_path}"; p="${p#chat/}"
  id="$(message_id "chat/$p")"
  [ -n "$id" ] || { echo "chat-queue: 取不到 $p 的 blob sha" >&2; exit 6; }
  msha="${id##*--}"
  key="$(local_key "chat/$p")"
  # v3 稳定竞争点：时间戳取 source message（不取当前时间），所有竞争者必须推出同一路径
  sts="$(source_ts "$p")" || { echo "  ERROR    推导不出稳定 source timestamp（文件名与正文都没有精确时间戳）—— fail closed，不领租约" >&2; exit 6; }
  cp="$(marker_path to-hermes claim "$p" "$sts")"
  claim_field() { # $1=远端文件 JSON  $2=正文字段名
    printf '%s' "$1" | json_get content | base64 -d 2>/dev/null | python3 -c "
import sys,json
try: d=json.loads(sys.stdin.read())
except Exception: d={}
print(d.get(sys.argv[1],'') if isinstance(d,dict) else '')
" "$2"
  }
  existing="$(api GET "$API/$cp?ref=$BRANCH")"
  sha="$(printf '%s' "$existing" | json_get sha)"
  if [ -z "$sha" ]; then
    # 稳定路径还是空的 → 先看有没有历史（按当前时间命名的旧 claim）已占这个 source，
    # 有就并入“已有 claim”分支，避免新旧两条路径各持一个 owner。
    legacy="$(/home/ubuntu/.hermes/scripts/chat-marker-index.py to-hermes 2>/dev/null \
      | awk -F'\t' -v w="$msha" '$1==w && $2=="claim" {print $3; exit}')"
    if [ -n "$legacy" ] && [ "$legacy" != "$cp" ]; then
      echo "  见历史 claim（非稳定路径，按正文 message_blob_sha 命中）：$legacy"
      cp="$legacy"; existing="$(api GET "$API/$cp?ref=$BRANCH")"; sha="$(printf '%s' "$existing" | json_get sha)"
    fi
  fi
  if [ -z "$sha" ]; then
    nonce="$(new_nonce)"
    body="$(python3 -c "
import json,sys
print(json.dumps({
 'protocol_version':3,'direction':'to-hermes','message_id':sys.argv[1],
 'message_path':sys.argv[2],'message_blob_sha':sys.argv[3],
 'owner':sys.argv[4],'claim_nonce':sys.argv[5],'claimed_at':sys.argv[6],
 'lease_until':sys.argv[7],'status':'processing'}, ensure_ascii=False, indent=2))
" "$id" "chat/$p" "$msha" "$OWNER_NAME" "$nonce" "$(now)" "$(now_plus_min $LEASE_MINUTES)")"
    r="$(put_file "$cp" "$body")"
    case "$r" in
      ok) printf '%s' "$nonce" > "$NONCE_DIR/$key"
          arm_lease "$key" "$p" "$nonce"
          echo "  GRANTED  $id"; echo "  稳定 claim 路径 $cp"
          echo "  租约至 $(now_plus_min $LEASE_MINUTES)　(lease_until)"; exit 0 ;;
      conflict) echo "  DENIED   已被别的 worker 抢先领走（create-file 冲突）—— 本轮跳过，不动手"; exit 1 ;;
      *) # 并发 create 竞态时 GitHub 可能返回 409/5xx 而非标准 422；二次确认后归类，
         # 只有「claim 仍不存在」才算真的网络/权限故障
         if [ -n "$(blob_sha "$cp")" ]; then
           echo "  DENIED   并发 create 冲突（错误响应后二次确认：claim 已被别人创建）—— 本轮跳过，不动手"; exit 1
         fi
         echo "  ERROR    取租约失败（网络/权限），按协议本轮不处理"; exit 6 ;;
    esac
  fi
  # 稳定路径已有 claim：正文 identity 必须精确对应本条 source，否则是命名碰撞 → ERROR，禁止覆盖
  rid="$(claim_field "$existing" message_id)"
  rsha="$(claim_field "$existing" message_blob_sha)"
  if { [ -n "$rid" ] && [ "$rid" != "$id" ]; } || { [ -n "$rsha" ] && [ "$rsha" != "$msha" ]; }; then
    echo "  ERROR    $cp 的正文 identity 与本消息不符（message_id=${rid:-空} / blob=${rsha:-空} ≠ $id）—— 命名碰撞或协议错误，本轮不动手" >&2
    exit 6
  fi
  # 已有 claim：过期才可 CAS 接管
  until_="$(claim_field "$existing" lease_until)"
  if [ -n "$until_" ] && [ "$until_" \> "$(now)" ]; then
    echo "  DENIED   租约仍有效（至 $until_）—— 本轮跳过"; exit 1
  fi
  nonce="$(new_nonce)"
  body="$(python3 -c "
import json,sys
print(json.dumps({
 'protocol_version':3,'direction':'to-hermes','message_id':sys.argv[1],
 'message_path':sys.argv[2],'message_blob_sha':sys.argv[3],
 'owner':sys.argv[4],'claim_nonce':sys.argv[5],'claimed_at':sys.argv[6],
 'lease_until':sys.argv[7],'status':'processing','took_over_expired_lease':True}, ensure_ascii=False, indent=2))
" "$id" "chat/$p" "$msha" "$OWNER_NAME" "$nonce" "$(now)" "$(now_plus_min $LEASE_MINUTES)")"
  r="$(put_file "$cp" "$body" "$sha")"
  if [ "$r" = "ok" ]; then
    printf '%s' "$nonce" > "$NONCE_DIR/$key"; arm_lease "$key" "$p" "$nonce"
    echo "  TAKEOVER $id（过期租约已 CAS 接管）"; exit 0
  fi
  echo "  DENIED   接管时 CAS 冲突（别人已先续租/接管）—— 本轮跳过"; exit 1
  ;;

complete)
  p="${1:?要传 message_path}"; p="${p#chat/}"
  st="${2:?status：resolved|rejected|non-request}"; ev="${3:-（未填依据）}"
  id="$(message_id "chat/$p")"
  [ -n "$id" ] || { echo "chat-queue: 取不到 blob sha" >&2; exit 6; }
  msha="${id##*--}"
  cp="$(marker_path to-hermes completed "$p")"
  key="$(local_key "chat/$p")"
  # v3：completion 名字带的是**创建时刻**，判重不能只看固定路径 —— 按正文 message_blob_sha 扫一遍已完成的
  prev="$(/home/ubuntu/.hermes/scripts/chat-marker-index.py to-hermes 2>/dev/null \
    | awk -F'\t' -v w="$msha" '$1==w && $2=="completed" {print $3; exit}')"
  [ -n "$prev" ] && cp="$prev"
  if [ -n "$(blob_sha "$cp")" ]; then
    echo "  已存在 completion marker，跳过（幂等）：$cp"
  else
    body="$(python3 -c "
import json,sys
print(json.dumps({
 'protocol_version':3,'direction':'to-hermes','message_id':sys.argv[1],
 'message_path':sys.argv[2],'message_blob_sha':sys.argv[3],
 'completed_at':sys.argv[4],'status':sys.argv[5],'evidence':sys.argv[6]},
 ensure_ascii=False, indent=2))
" "$id" "chat/$p" "$msha" "$(now)" "$st" "$ev")"
    r="$(put_file "$cp" "$body")"
    [ "$r" = "ok" ] || { echo "  ERROR/冲突：写 marker 失败（$r）"; exit 6; }
    echo "  已写 completion marker：$cp"
  fi
  # 同步本地快速过滤器（poller 用；仓库内的 marker 才是权威）
  sha="$msha"
  grep -qxF "$sha" "$PROCESSED_LIST" 2>/dev/null || echo "$sha" >> "$PROCESSED_LIST"
  echo "  本地过滤器已同步（$sha）"
  # 释放本地租约凭据：watchdog 每 tick 看它，文件消失即退出（不再对已完成消息续租）
  rm -f "$NONCE_DIR/$key" "$NONCE_DIR/$key.meta" "$NONCE_DIR/$key.watch.pid"
  echo "  已释放本地租约凭据（watchdog 随即退出）"
  ;;

status-append)
  row="${1:?要传账本行}"
  # C 类共享写：RESOURCE_LEASE_PROTOCOL.md 要求改 STATUS.md 必须同时持 resource:chat/STATUS.md；
  # resource lease 与文件 blob SHA CAS 是两层保护，不互相替代（先拿 lease，再 CAS 写）。
  RLE="/home/ubuntu/.hermes/scripts/chat-resource-lease.py"
  rl_out="$("$RLE" acquire resource:chat/STATUS.md "$OWNER_NAME" "status-append" 300 2>&1)"; rl_rc=$?
  echo "  [resource-lease] $rl_out"
  if [ "$rl_rc" != "0" ]; then
    echo "  未取得 resource:chat/STATUS.md 的 lease（rc=$rl_rc：10=BUSY 排队 / 20=故障）—— 按协议不写账本，交回调用方重试" >&2
    exit "$rl_rc"
  fi
  rl_nonce="$(printf '%s' "$rl_out" | sed -nE 's/.*holder_nonce=([^ ]+).*/\1/p')"
  rl_fence="$(printf '%s' "$rl_out" | sed -nE 's/.*fence=([0-9]+).*/\1/p')"
  rl_release() {
    [ -n "${rl_nonce:-}" ] && [ -n "${rl_fence:-}" ] || return 0
    "$RLE" release resource:chat/STATUS.md "$rl_nonce" "$rl_fence" 2>&1 | sed 's/^/  [resource-lease] /'
  }
  for attempt in 1 2 3; do
    cur="$(api GET "$API/chat/STATUS.md?ref=$BRANCH")"
    sha="$(printf '%s' "$cur" | json_get sha)"
    printf '%s' "$(api GET "$API/chat/STATUS.md?ref=$BRANCH" | json_get content | base64 -d 2>/dev/null)" > "$TMP/STATUS.md"
    # 边界保护：若文件末尾没有换行，直接追加会把新行粘在最后一行上（实测发生过，
    # 导致账本行首竖线被"吃掉"，由轮询任务事后手工修复）。这里先补一个换行。
    if [ -s "$TMP/STATUS.md" ] && [ -n "$(tail -c1 "$TMP/STATUS.md")" ]; then
      printf '\n' >> "$TMP/STATUS.md"
    fi
    printf '%s\n' "$row" >> "$TMP/STATUS.md"
    body="$(python3 -c "
import json,sys,base64
c=open(sys.argv[1],'rb').read()
print(json.dumps({'message':sys.argv[2],'content':base64.b64encode(c).decode(),'sha':sys.argv[3],'branch':sys.argv[4]}))
" "$TMP/STATUS.md" "chat($OWNER_NAME): STATUS append" "$sha" "$BRANCH")"
    r="$(put_file "chat/STATUS.md" "$(cat "$TMP/STATUS.md")" "$sha")"
    if [ "$r" = "ok" ]; then
      echo "  账本行已追加（第 ${attempt} 次尝试成功，基于 blob SHA CAS）"
      rl_release
      exit 0
    fi
    echo "  第 ${attempt} 次 CAS 冲突（别人同时改了账本）→ 重取最新、保留其新行后重试"
    sleep 2
  done
  echo "  STATUS 追加 3 次均冲突，未覆盖任何人 —— 交回人工" >&2
  rl_release
  exit 4
  ;;

resource-lease)
  # 共享资源 lease：转交协议客户端（协议 chat/RESOURCE_LEASE_PROTOCOL.md，退出码 0/10/11/20）
  exec /home/ubuntu/.hermes/scripts/chat-resource-lease.py "$@"
  ;;

path-of)
  # 只读诊断：打印标记路径。claim 路径必须与时钟无关（v3 稳定竞争点），便于回归测试。
  what="${1:?state：claim|completed}"; p="${2:?要传 message_path}"; p="${p#chat/}"
  case "$what" in
    claim) sts="$(source_ts "$p")" || { echo "  ERROR    推导不出稳定 source timestamp —— fail closed" >&2; exit 6; }
           marker_path to-hermes claim "$p" "$sts" ;;
    completed) marker_path to-hermes completed "$p" ;;
    *) echo "path-of: state 只能是 claim|completed" >&2; exit 2 ;;
  esac
  ;;

renew)
  # 续租：验证我是本 claim 的持有者（本地 nonce == 远端 claim_nonce），再基于当前 blob SHA CAS 延长 lease_until
  p="${1:?要传 message_path}"; p="${p#chat/}"
  id="$(message_id "chat/$p")"
  [ -n "$id" ] || { echo "chat-queue: 取不到 $p 的 blob sha" >&2; exit 6; }
  key="$(local_key "chat/$p")"
  find_claim() { # 按正文 message_blob_sha 找 claim 文件（名字不再承担对账）
    local want; want="$(blob_sha "chat/$p")"
    /home/ubuntu/.hermes/scripts/chat-marker-index.py to-hermes 2>/dev/null \
      | awk -F'\t' -v w="$want" '$1==w && $2=="claim" {print $3; exit}'
  }
  cp="$(find_claim)"
  [ -n "$cp" ] || { echo "  没有 claim，不能续租（先 claim）" >&2; exit 6; }
  cur="$(api GET "$API/$cp?ref=$BRANCH")"
  sha="$(printf '%s' "$cur" | json_get sha)"
  [ -n "$sha" ] || { echo "  claim 读不到 blob sha，不能续租" >&2; exit 6; }
  printf '%s' "$cur" | python3 -c "
import sys,json,base64
d=json.load(sys.stdin); sys.stdout.write(base64.b64decode(d['content']).decode('utf-8'))
" > "$TMP/claim.json" 2>/dev/null || { echo "  远端 claim 解析失败" >&2; exit 6; }
  local_nonce="$(cat "$NONCE_DIR/$key" 2>/dev/null || true)"
  remote_nonce="$(json_get claim_nonce < "$TMP/claim.json")"
  if [ -z "$local_nonce" ] || [ "$local_nonce" != "$remote_nonce" ]; then
    echo "  DENIED   nonce 校验失败（本地凭据与远端 claim 不一致，或已被别人接管）—— 不续租"; exit 1
  fi
  until_="$(json_get lease_until < "$TMP/claim.json")"
  if [ -n "$until_" ] && [ "$until_" \< "$(now)" ]; then
    echo "  DENIED   租约已过期（lease_until=$until_）—— 续租窗口已过，重新 claim 会走过期接管路径"; exit 1
  fi
  if [ -n "$until_" ] && [ "$(now_plus_min $LEASE_MINUTES)" \< "$until_" ]; then
    echo "  租约已覆盖到 $until_（本次不缩短，跳过续租）"; exit 0
  fi
  body="$(python3 - "$TMP/claim.json" "$(now_plus_min $LEASE_MINUTES)" "$(now)" <<'PY'
import sys,json
d=json.load(open(sys.argv[1]))
d['lease_until']=sys.argv[2]
d['renewed_at']=sys.argv[3]
print(json.dumps(d,ensure_ascii=False,indent=2))
PY
)"
  r="$(put_file "$cp" "$body" "$sha")"
  if [ "$r" = "ok" ]; then
    echo "  RENEWED $id"; echo "  新租约至 $(now_plus_min $LEASE_MINUTES)（CAS 基于旧 blob sha ${sha:0:12}）"; exit 0
  fi
  echo "  DENIED   续租 CAS 冲突（别人已先续租/接管）—— 本轮放弃"; exit 1
  ;;

lease-state)
  # 供会话层问一句"我还持有吗"。renew 失败（CAS 冲突/nonce 不一致）会写 .lost 标记并清凭据。
  p="${1:?要传 message_path}"; p="${p#chat/}"
  id="$(message_id "chat/$p")"
  [ -n "$id" ] || { echo "chat-queue: 取不到 blob sha" >&2; exit 6; }
  key="$(local_key "chat/$p")"
  if [ -f "$NONCE_DIR/$key.lost" ]; then
    echo "  lost    已失去所有权（续租失败）—— 按协议停止产生新的不可逆副作用，进入 reconcile"
    cat "$NONCE_DIR/$key.lost"
    exit 3
  fi
  if [ -f "$NONCE_DIR/$key" ]; then
    echo "  held    本地持有凭据 nonce=$(cat "$NONCE_DIR/$key")"
    [ -f "$NONCE_DIR/$key.meta" ] && cat "$NONCE_DIR/$key.meta"
    exit 0
  fi
  echo "  none    本地无凭据（未领 / 已完成 / 凭据丢失）—— 凭据丢失按协议走租约到期后的 CAS 接管"
  exit 1
  ;;

__watchdog)
  # 内部子命令（claim 成功后自动 fork）。到 RENEW_AFTER_SEC 检查任务是否仍在跑，仍在就跑 renew。
  id="${1:?}"; p="${2:?}"; anchor="${3:?}"; watch_pid="${4:-0}"
  LOG="$NONCE_DIR/$id.watch.log"
  log() { printf '%s  [watchdog pid=%s] %s\n' "$(now)" "$$" "$*" >> "$LOG"; }
  log "启动：租约 id=$id anchor_epoch=$anchor 任务进程=$watch_pid 续租阈值=${RENEW_AFTER_SEC}s tick=${WATCHDOG_TICK_SEC}s"
  start="$(date +%s)"
  while :; do
    sleep "$WATCHDOG_TICK_SEC"
    if [ ! -f "$NONCE_DIR/$id" ]; then log "本地凭据已释放（完成或失权），退出"; exit 0; fi
    if [ "$watch_pid" != "0" ] && ! kill -0 "$watch_pid" 2>/dev/null; then
      log "任务进程 $watch_pid 已退出，无需续租，退出"; exit 0
    fi
    nows="$(date +%s)"
    if [ $((nows - start)) -ge "$WATCHDOG_MAX_SEC" ]; then log "达到自保上限 ${WATCHDOG_MAX_SEC}s，退出"; exit 0; fi
    if [ $((nows - anchor)) -ge "$RENEW_AFTER_SEC" ]; then
      out="$("$SELF" renew "$p" 2>&1)"; rc=$?
      printf '%s  [watchdog] renew rc=%s: %s\n' "$(now)" "$rc" "$out" >> "$LOG"
      if [ "$rc" = "0" ]; then
        anchor="$nows"; log "续租成功，锚点更新到 epoch=$anchor"
      else
        log "续租失败 → 按协议视为失去所有权：清本地凭据 + 写 .lost 标记，停止新副作用"
        printf '%s\n' "$out" > "$NONCE_DIR/$id.lost"
        printf 'lost_at=%s\n' "$(now)" >> "$NONCE_DIR/$id.lost"
        rm -f "$NONCE_DIR/$id"
        exit 1
      fi
    fi
  done
  ;;

*)
  echo "用法：chat-queue.sh {list|claim <path>|renew <path>|lease-state <path>|path-of claim|completed <path>|complete <path> <status> <evidence>|status-append \"<row>\"}" >&2
  exit 2 ;;
esac
