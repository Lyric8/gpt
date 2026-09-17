#!/usr/bin/env bash
# No credentials are accepted on argv. Weixin delivery belongs to the gateway
# worker; remote alert delivery is a separate GitHub control-plane path.
set -euo pipefail
umask 077
: "${HERMES_HOME:=$HOME/.hermes}"
: "${HERMES_ROOT:=$HERMES_HOME/hermes-agent}"
: "${HERMES_PYTHON:=$HERMES_ROOT/venv/bin/python}"
: "${WX_PROFILE:=default}"

alert_tool="$HERMES_HOME/scripts/wx_outbox_alert.py"

case "${1:-health}" in
  health)
    : "${WX_ACCOUNT_ID:?set the existing non-secret account id}"
    cd "$HERMES_ROOT"
    exec "$HERMES_PYTHON" -m gateway.wx_outbox_cli \
      --db "$HERMES_HOME/state.db" --account "$WX_ACCOUNT_ID" --profile "$WX_PROFILE" watchdog
    ;;
  collect)
    : "${WX_ACCOUNT_ID:?set the existing non-secret account id}"
    : "${WX_CHAT_ID:?set the existing non-secret destination id}"
    : "${WX_ACTIVATION_EPOCH:?explicit deployment watermark required}"
    cd "$HERMES_ROOT"
    common=(--db "$HERMES_HOME/state.db" --account "$WX_ACCOUNT_ID" --profile "$WX_PROFILE")
    "$HERMES_PYTHON" -m gateway.wx_outbox_cli "${common[@]}" queue-import \
      --directory "$HERMES_HOME/cache/notify-queue" --chat "$WX_CHAT_ID" --writers-stopped
    exec "$HERMES_PYTHON" -m gateway.wx_outbox_cli "${common[@]}" collect-cron \
      --directory "$HERMES_HOME/cron/output" --chat "$WX_CHAT_ID" --since-epoch "$WX_ACTIVATION_EPOCH"
    ;;
  alert-observe)
    : "${WX_ACCOUNT_ID:?set the existing non-secret account id}"
    exec "$HERMES_PYTHON" "$alert_tool" observe
    ;;
  alert-drain)
    exec "$HERMES_PYTHON" "$alert_tool" drain
    ;;
  heartbeat)
    exec "$HERMES_PYTHON" "$alert_tool" heartbeat
    ;;
  *)
    echo 'usage: outbox-ops.sh health|collect|alert-observe|alert-drain|heartbeat' >&2
    exit 64
    ;;
esac
