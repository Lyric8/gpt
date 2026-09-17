#!/usr/bin/env bash
# No credentials. All delivery belongs to the gateway worker.
set -euo pipefail
umask 077
: "${HERMES_HOME:=$HOME/.hermes}"
: "${HERMES_ROOT:=$HERMES_HOME/hermes-agent}"
: "${HERMES_PYTHON:=$HERMES_ROOT/venv/bin/python}"
: "${WX_ACCOUNT_ID:?set the existing non-secret account id}"
: "${WX_CHAT_ID:?set the existing non-secret destination id}"
: "${WX_PROFILE:=default}"
cd "$HERMES_ROOT"
common=(--db "$HERMES_HOME/state.db" --account "$WX_ACCOUNT_ID" --profile "$WX_PROFILE")
case "${1:-health}" in
  health) exec "$HERMES_PYTHON" -m gateway.wx_outbox_cli "${common[@]}" watchdog ;;
  collect)
    : "${WX_ACTIVATION_EPOCH:?explicit deployment watermark required}"
    "$HERMES_PYTHON" -m gateway.wx_outbox_cli "${common[@]}" queue-import \
      --directory "$HERMES_HOME/cache/notify-queue" --chat "$WX_CHAT_ID" --writers-stopped
    exec "$HERMES_PYTHON" -m gateway.wx_outbox_cli "${common[@]}" collect-cron \
      --directory "$HERMES_HOME/cron/output" --chat "$WX_CHAT_ID" --since-epoch "$WX_ACTIVATION_EPOCH" ;;
  *) echo 'usage: outbox-ops.sh health|collect' >&2; exit 64 ;;
esac
