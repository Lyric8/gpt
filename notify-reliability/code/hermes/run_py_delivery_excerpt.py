# 抽取：gateway/run.py 中与「最终回复交付」相关的段落（行号见每段标题）

## 关键字: delivery_ledger
  12841:        Crash-ambiguity contract (see gateway/delivery_ledger.py):
  12847:            from gateway.delivery_ledger import (
  12904:            from gateway.delivery_ledger import (
  13018:            from gateway.delivery_ledger import (

## 关键字: Sending response

## 关键字: sweep_recoverable
  12849:                sweep_recoverable,
  12875:                sweep_recoverable,

## 关键字: sweep_failed_for_runtime
  13021:                sweep_failed_for_runtime,
  13027:                sweep_failed_for_runtime,

## 上下文（delivery_ledger 调用点前后 40 行）

### 行 12841 附近
        self, claimed: list, *, require_success: bool = False
    ) -> list:
        """Clear resume flags and return rows safe to redeliver.

        Startup recovery preserves its historical best-effort behavior. Runtime
        reconnect recovery is stricter: if the session-store write fails, the
        corresponding response must not be sent because the same agent turn
        could otherwise be resumed immediately afterward.
        """
        sendable = []
        for row in claimed:
            session_key = row.get("session_key") or ""
            if not session_key:
                sendable.append(row)
                continue
            try:
                await self.async_session_store.clear_resume_pending(session_key)
            except Exception:
                logger.debug(
                    "clear_resume_pending failed for %s", session_key,
                    exc_info=True,
                )
                if not require_success:
                    sendable.append(row)
            else:
                sendable.append(row)
        return sendable

    async def _claim_pending_obligations(self) -> list:
        """Claim recoverable delivery-ledger rows and clear their
        ``resume_pending`` flags. Pure DB work — no network sends.

        Runs INLINE at startup BEFORE ``_schedule_resume_pending_sessions``
        and before the (bounded, abandonable) boot-send task exists. A
        session with a recoverable obligation already produced its answer —
        the turn completed and only delivery is owed — so clearing
        ``resume_pending`` here prevents the resume path from re-running
        (and re-paying for) a turn whose output we hold, regardless of how
        long the sends ahead of redelivery take (#91969).

        Crash-ambiguity contract (see gateway/delivery_ledger.py):
        rows that were mid-send or previously rejected carry a visible
        recovered-reply marker so a possible duplicate is labeled, never
        silent. Returns the claimed rows for redelivery.
        """
        try:
            from gateway.delivery_ledger import (
                ledger_enabled,
                sweep_recoverable,
            )

            if not await asyncio.to_thread(ledger_enabled):
                return []
            # Only claim rows whose exact transport owner is connected this
            # boot. A multiplexed gateway can host several bot identities for
            # one platform; platform-only filtering would spend a disconnected
            # bot's retry budget merely because another bot is online.
            _profile_adapters = getattr(self, "_profile_adapters", None) or {}
            _deliverable_targets = {
                (getattr(p, "value", str(p)), "default") for p in self.adapters
            }
            # Legacy rows predate adapter_profile. They are unambiguous only in
            # a non-multiplexed gateway; fail closed when multiple bot identities
            # share the process.
            if not _profile_adapters:
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), None) for p in self.adapters
                )
            for _profile, _adapters in _profile_adapters.items():
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), _profile) for p in _adapters
                )
            _deliverable = {platform for platform, _ in _deliverable_targets}
            claimed = await asyncio.to_thread(
                sweep_recoverable,
                None,
                deliverable_platforms=_deliverable,
                deliverable_targets=_deliverable_targets,
            )
        except Exception:
            logger.debug("delivery ledger sweep failed", exc_info=True)

### 行 12847 附近
        corresponding response must not be sent because the same agent turn
        could otherwise be resumed immediately afterward.
        """
        sendable = []
        for row in claimed:
            session_key = row.get("session_key") or ""
            if not session_key:
                sendable.append(row)
                continue
            try:
                await self.async_session_store.clear_resume_pending(session_key)
            except Exception:
                logger.debug(
                    "clear_resume_pending failed for %s", session_key,
                    exc_info=True,
                )
                if not require_success:
                    sendable.append(row)
            else:
                sendable.append(row)
        return sendable

    async def _claim_pending_obligations(self) -> list:
        """Claim recoverable delivery-ledger rows and clear their
        ``resume_pending`` flags. Pure DB work — no network sends.

        Runs INLINE at startup BEFORE ``_schedule_resume_pending_sessions``
        and before the (bounded, abandonable) boot-send task exists. A
        session with a recoverable obligation already produced its answer —
        the turn completed and only delivery is owed — so clearing
        ``resume_pending`` here prevents the resume path from re-running
        (and re-paying for) a turn whose output we hold, regardless of how
        long the sends ahead of redelivery take (#91969).

        Crash-ambiguity contract (see gateway/delivery_ledger.py):
        rows that were mid-send or previously rejected carry a visible
        recovered-reply marker so a possible duplicate is labeled, never
        silent. Returns the claimed rows for redelivery.
        """
        try:
            from gateway.delivery_ledger import (
                ledger_enabled,
                sweep_recoverable,
            )

            if not await asyncio.to_thread(ledger_enabled):
                return []
            # Only claim rows whose exact transport owner is connected this
            # boot. A multiplexed gateway can host several bot identities for
            # one platform; platform-only filtering would spend a disconnected
            # bot's retry budget merely because another bot is online.
            _profile_adapters = getattr(self, "_profile_adapters", None) or {}
            _deliverable_targets = {
                (getattr(p, "value", str(p)), "default") for p in self.adapters
            }
            # Legacy rows predate adapter_profile. They are unambiguous only in
            # a non-multiplexed gateway; fail closed when multiple bot identities
            # share the process.
            if not _profile_adapters:
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), None) for p in self.adapters
                )
            for _profile, _adapters in _profile_adapters.items():
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), _profile) for p in _adapters
                )
            _deliverable = {platform for platform, _ in _deliverable_targets}
            claimed = await asyncio.to_thread(
                sweep_recoverable,
                None,
                deliverable_platforms=_deliverable,
                deliverable_targets=_deliverable_targets,
            )
        except Exception:
            logger.debug("delivery ledger sweep failed", exc_info=True)
            return []
        if not claimed:
            return []

        # Clear resume_pending for EVERY claimed row up front, before any
        # send. Claiming already spent one of the row's redelivery attempts —

### 行 12904 附近
            # share the process.
            if not _profile_adapters:
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), None) for p in self.adapters
                )
            for _profile, _adapters in _profile_adapters.items():
                _deliverable_targets.update(
                    (getattr(p, "value", str(p)), _profile) for p in _adapters
                )
            _deliverable = {platform for platform, _ in _deliverable_targets}
            claimed = await asyncio.to_thread(
                sweep_recoverable,
                None,
                deliverable_platforms=_deliverable,
                deliverable_targets=_deliverable_targets,
            )
        except Exception:
            logger.debug("delivery ledger sweep failed", exc_info=True)
            return []
        if not claimed:
            return []

        # Clear resume_pending for EVERY claimed row up front, before any
        # send. Claiming already spent one of the row's redelivery attempts —
        # the answer is in the ledger, so the resume path must never re-run
        # these turns (#91969).
        await self._clear_resume_pending_for_claimed_obligations(claimed)
        return claimed

    async def _redeliver_claimed_obligations(self, claimed: list) -> int:
        """Redeliver final responses for rows already claimed (and
        resume-cleared) by :meth:`_claim_pending_obligations`.

        Network half of the split — runs inside the bounded boot-send task,
        so a flood-limited send can be abandoned by the restore gate without
        reopening the turn-replay window. Returns redeliveries attempted.
        """
        if not claimed:
            return 0
        try:
            from gateway.delivery_ledger import (
                RECOVERED_MARKER,
                mark_delivered,
                mark_failed,
                release_runtime_claim,
            )
        except Exception:
            logger.debug("delivery ledger import failed", exc_info=True)
            return 0

        redelivered = 0
        for row in claimed:
            try:
                platform = Platform(row["platform"])
            except Exception:
                logger.debug(
                    "obligation %s: unknown platform %r",
                    row["obligation_id"], row.get("platform"),
                )
                continue
            if "profile" in row:
                adapter = self._authorization_adapter(
                    platform, row.get("profile")
                )
            else:
                # Startup rows preserve the historical default-adapter route.
                adapter = self.adapters.get(platform)
            if adapter is None:
                # Runtime claims have not reached a transport yet. If the
                # reconnect vanished before dispatch, release the claim without
                # spending an attempt so the next reconnect can retry it.
                if row.get("runtime_recovery"):
                    try:
                        await asyncio.to_thread(
                            release_runtime_claim,
                            row["obligation_id"],
                            "send_path_degraded",
                        )
                    except Exception:
                        logger.debug(
                            "failed to release undispatched runtime obligation %s",
