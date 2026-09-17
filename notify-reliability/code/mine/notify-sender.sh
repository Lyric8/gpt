#!/usr/bin/env bash
# 通讯系统唯一发送者（systemd 常驻，20~30 秒一轮；stdout 不用于投递，全部走 hermes send）
#
# 设计要点（每一条都对应一次真实事故）：
#   1) **自己拆片**：微信单条上限 2000 字符。整段丢给平台，平台会拆成多条**连着**发，
#      一次性冲爆 iLink 限流 → 整条丢失。所以这里自己按段拆成 ≤1900 字，**每轮只发一片**，
#     天然错开（配合熔断节流），并记录已发到第几片：失败/重启后从断点继续，不重不漏。
#   2) **失败必重发**：条目只在整段发完后才出队；任何一片失败就留在队列，下一轮重试。
#   3) **对话回复也有兜底**：outbox 里登记的回复，若其发送窗口内网关日志出现发送失败，
#      就转入队列重发；没有失败记录则视为已送达、清掉登记 —— 只在真失败时补发，不制造重复。
#   4) 熔断保护：日志里 60 秒内出现过发送失败 → 本轮什么都不发。
#   5) 崩溃上报 + 评估层心跳自检（坏了要有人喊）。
set -uo pipefail

HOME_DIR="${HOME:-/home/ubuntu}"
QUEUE="$HOME_DIR/.hermes/cache/notify-queue"
OUTBOX="$QUEUE/outbox"
OUTROOT="$HOME_DIR/.hermes/cron/output"
JOBS="$HOME_DIR/.hermes/cron/jobs.json"
DELIVERED="$QUEUE/delivered.log"
GWLOG="$HOME_DIR/.hermes/logs/gateway.log"
HB_EVAL="$HOME_DIR/.hermes/cache/campfire-eval-heartbeat"
HB_SELF="$HOME_DIR/.hermes/cache/notify-sender-heartbeat"
ALERT_STAMP="$QUEUE/last_alert_at"
SELF_ID_FILE="$QUEUE/self_job_id"
HERMES_BIN="$(command -v hermes 2>/dev/null || echo "$HOME_DIR/.local/bin/hermes")"
[ -x "$HERMES_BIN" ] || HERMES_BIN="$HOME_DIR/.hermes/hermes-agent/venv/bin/hermes"
TARGET="weixin"
CHUNK=1900            # 每片字符上限（微信 2000，留余量）
THROTTLE_S=60         # 静默窗口：最近一次发送失败距今不足这么多秒 → 本轮不发
OUTBOX_GRACE_S=120    # 登记的回复：窗口后才判定
OUTBOX_WIN_S=240      # 判定窗口长度
ALERT_AFTER_MIN=15
ALERT_REPEAT_MIN=60

mkdir -p "$QUEUE" "$OUTBOX"; touch "$DELIVERED"

python3 - "$QUEUE" "$OUTBOX" "$OUTROOT" "$JOBS" "$DELIVERED" "$GWLOG" "$HB_EVAL" "$HB_SELF" \
         "$ALERT_STAMP" "$SELF_ID_FILE" "$TARGET" "$HERMES_BIN" \
         "$CHUNK" "$THROTTLE_S" "$OUTBOX_GRACE_S" "$OUTBOX_WIN_S" "$ALERT_AFTER_MIN" "$ALERT_REPEAT_MIN" <<'PY'
import sys, os, re, json, glob, hashlib, datetime, subprocess

(queue, outbox, outroot, jobs_p, delivered_p, gwlog_p, hb_eval, hb_self,
 alert_p, self_id_f, target, hermes_bin, CHUNK, THROTTLE_S, GRACE_S, WIN_S,
 ALERT_AFTER, ALERT_REPEAT) = sys.argv[1:19]
CHUNK, THROTTLE_S, GRACE_S, WIN_S = int(CHUNK), int(THROTTLE_S), int(GRACE_S), int(WIN_S)
ALERT_AFTER, ALERT_REPEAT = int(ALERT_AFTER), int(ALERT_REPEAT)
now = datetime.datetime.now().astimezone()
TZ = now.tzinfo

def sha16(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]
def delivered_set(): return set(l.strip() for l in open(delivered_p, encoding='utf-8') if l.strip())
def read(p):
    try: return open(p, encoding='utf-8', errors='replace').read()
    except Exception: return ''

def split_chunks(text, limit=CHUNK):
    """按段拆片：优先空行，其次单行，最后硬切；不切断代码围栏。"""
    text = text.strip()
    if len(text) <= limit: return [text]
    out, buf = [], ''
    def flush():
        nonlocal buf
        if buf.strip(): out.append(buf.rstrip())
        buf = ''
    for para in re.split(r'(\n\s*\n)', text):
        if buf and len(buf) + len(para) > limit:
            flush()
        if len(para) <= limit:
            buf += para
        else:  # 单段就超限 → 按行再拆，再不行硬切
            for line in para.splitlines(keepends=True):
                if len(buf) + len(line) > limit: flush()
                if len(line) <= limit:
                    buf += line
                else:
                    for i in range(0, len(line), limit):
                        piece = line[i:i+limit]
                        if len(buf) + len(piece) > limit: flush()
                        buf += piece
    flush()
    return out or [text[:limit]]

def send(text):
    """返回 (ok, err)。临时文件交给 hermes send，避免命令行长度问题。"""
    p = '/tmp/notify-chunk.txt'
    open(p, 'w', encoding='utf-8').write(text)
    try:
        r = subprocess.run([hermes_bin, 'send', '--to', target, '-f', p, '--json'],
                           capture_output=True, text=True, timeout=180)
        try: res = json.loads(r.stdout or '{}')
        except Exception: res = {}
        return (bool(res.get('success')) and r.returncode == 0,
                (res.get('error') or r.stderr or '')[:200].replace('\n', ' '))
    except Exception as e:
        return (False, str(e)[:200])

def send_failures():
    out = []
    for line in read(gwlog_p).splitlines():
        if '[Weixin] send failed' in line:
            m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if m:
                try: out.append(datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ))
                except Exception: pass
    return out

fails = send_failures()
last_fail = max(fails) if fails else None

# ── 1. outbox：只在「登记之后确实发失败过」才补发 ────────────────
for tf in sorted(glob.glob(os.path.join(outbox, '*.txt'))):
    base = os.path.basename(tf)[:-4]
    meta = os.path.join(outbox, base + '.staged')
    if not os.path.exists(meta):
        os.remove(tf); continue
    try:
        staged = datetime.datetime.fromisoformat(read(meta).strip())
    except Exception:
        staged = datetime.datetime.fromtimestamp(os.path.getmtime(tf), tz=TZ)
    age = (now - staged).total_seconds()
    if age < GRACE_S:      # 还没到判定时刻（回复刚发出，结果未知）→ 留着
        continue
    win_end = staged + datetime.timedelta(seconds=WIN_S)
    hit = any(staged <= f <= win_end for f in fails)
    if hit and age <= WIN_S + 600:
        body = read(tf).strip()
        h = sha16(body)
        if h not in delivered_set():
            open(os.path.join(queue, '%s-%s.txt' % (now.strftime('%Y%m%dT%H%M%S'), h)), 'w',
                 encoding='utf-8').write('【补发·上一条被限流吞了】\n\n' + body + '\n')
    for p in (tf, meta):
        if os.path.exists(p): os.remove(p)

# ── 2. 收集定时任务的新输出（deliver=local，框架不再直发）────────
def load_jobs():
    try:
        d = json.load(open(jobs_p, encoding='utf-8'))
        js = d if isinstance(d, list) else d.get('jobs', d)
        return list(js.values()) if isinstance(js, dict) else (js or [])
    except Exception:
        return []

def enqueue(body, tag=''):
    h = sha16(body)
    if h in delivered_set(): return False
    for f in glob.glob(os.path.join(queue, '*.txt')):
        if f.endswith('-%s.txt' % h): return False
    text = (tag + '\n\n' if tag else '') + body.strip() + '\n'
    open(os.path.join(queue, '%s-%s.txt' % (now.strftime('%Y%m%dT%H%M%S'), h)), 'w',
         encoding='utf-8').write(text)
    return True

self_id = read(self_id_f).strip()
for j in load_jobs():
    jid = j.get('id') or ''
    if not jid or jid == self_id: continue
    files = sorted(glob.glob(os.path.join(outroot, jid, '*.md')), key=os.path.getmtime)
    if not files: continue
    txt = read(files[-1])
    marks = [m.start() for m in re.finditer(r'(?m)^##\s*Response\s*$', txt)]
    if not marks: continue                       # 空转留档：没有最终回复
    body = txt[marks[-1]:].split('\n', 1)[1].strip()
    if not body or body.startswith('# Cron Job:'): continue
    flat = re.sub(r'\s+', '', body)
    if flat.startswith('[SILENT]') and len(flat) < 40: continue
    enqueue(body, '【通知·%s】' % (j.get('name') or jid)[:14])

# ── 3. 崩溃上报 ────────────────────────────────────────────────
CRASH_LOG = os.path.join(os.path.dirname(queue), 'sender-crash.log')
CRASH_MARK = os.path.join(os.path.dirname(queue), 'sender-crash-pending')
if os.path.exists(CRASH_MARK):
    tail = read(CRASH_LOG).strip().split('---')[-2][-500:] if read(CRASH_LOG).count('---') else read(CRASH_LOG)[-500:]
    enqueue('⚠️ 通知发送者崩过一次（已由 systemd 重启，队列未丢）。报错尾部：\n\n' + tail.strip())
    os.remove(CRASH_MARK)

# ── 4. 评估层心跳自检 ──────────────────────────────────────────
if os.path.exists(hb_eval):
    age_min = (now.timestamp() - os.path.getmtime(hb_eval)) / 60.0
    if age_min > ALERT_AFTER:
        last = 0.0
        if os.path.exists(alert_p):
            try: last = float(read(alert_p).strip())
            except Exception: last = 0.0
        if (now.timestamp() - last) / 60.0 > ALERT_REPEAT:
            enqueue('⚠️ 通讯系统自检：轮询评估层已 %.0f 分钟没有心跳 —— 新消息可能叫不醒我。' % age_min)
            open(alert_p, 'w').write(str(now.timestamp()))

# ── 5. 熔断保护 ────────────────────────────────────────────────
if last_fail is not None and (now - last_fail).total_seconds() < THROTTLE_S:
    open(hb_self, 'w').write('%s throttle=yes（最近 %.0fs 内有发送失败）\n'
                             % (now.strftime('%Y-%m-%dT%H:%M:%S%z'), (now-last_fail).total_seconds()))
    sys.exit(0)

# ── 6. 发送：每轮只发**一片**，断点续传 ────────────────────────
items = sorted(f for f in glob.glob(os.path.join(queue, '*.txt'))
               if re.match(r'^\d{8}T\d{6}-[0-9a-f]+\.txt$', os.path.basename(f)))
items = [f for f in items if not os.path.exists(f + '.done')]
if not items:
    open(hb_self, 'w').write('%s idle depth=0\n' % now.strftime('%Y-%m-%dT%H:%M:%S%z'))
    sys.exit(0)

head = items[0]
body = read(head)
chunks = split_chunks(body)
prog_p = head + '.part'
try: done = int(read(prog_p).strip() or 0)
except Exception: done = 0

ok, err = send(chunks[done])
if ok:
    done += 1
    if done >= len(chunks):
        h = re.search(r'-([0-9a-f]+)\.txt$', os.path.basename(head)).group(1)
        open(delivered_p, 'a', encoding='utf-8').write(h + '\n')
        os.remove(head)
        for p in (prog_p,):
            if os.path.exists(p): os.remove(p)
        open(hb_self, 'w').write('%s sent=ok 整条完成 共%d片 depth=%d\n'
                                 % (now.strftime('%Y-%m-%dT%H:%M:%S%z'), len(chunks), len(items) - 1))
    else:
        open(prog_p, 'w').write(str(done))
        open(hb_self, 'w').write('%s sent=ok 第%d/%d片 depth=%d\n'
                                 % (now.strftime('%Y-%m-%dT%H:%M:%S%z'), done, len(chunks), len(items)))
else:
    open(hb_self, 'w').write('%s sent=fail 第%d/%d片 depth=%d err=%s\n'
                             % (now.strftime('%Y-%m-%dT%H:%M:%S%z'), done + 1, len(chunks), len(items), err))
    with open(os.path.join(os.path.dirname(queue), 'sender-errors.log'), 'a', encoding='utf-8') as f:
        f.write('%s chunk %d/%d failed: %s\n' % (now.strftime('%Y-%m-%dT%H:%M:%S%z'), done + 1, len(chunks), err))
PY
