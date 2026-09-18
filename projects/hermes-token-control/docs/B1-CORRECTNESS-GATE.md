# B1 action-boundary correctness gate

Status: code candidate, not deployed.  Base: `e6f07d2ce7915146cd67c49f769ed37e54a84b62`.

## Why this exists

The Stage-1 scanner deliberately does not wake an agent or execute business work. That is safe for shadow observation, but it leaves a correctness hole as soon as a dispatcher is connected: a local `PENDING` row is only a cached observation. Remote Git completion or STATUS may have changed after the scan and before a claim or side effect.

The authority rule is therefore:

```text
local SQLite state != execution authority
source identity = source_path + source_blob_sha
remote Git readback must succeed immediately before every action boundary
unknown remote state => fail closed
```

`remote_gate.py` and `dispatcher.py` implement that rule without adding a model call and without replacing the current chat message/resource lease protocol.

## Components

### `remote_gate.ActionBoundaryGate`

For one immutable source identity it:

1. fetches a fresh `chat` branch snapshot into a **dedicated non-shallow bare cache**. A pre-existing shallow gate cache is converged with `git fetch --unshallow` while the gate-local lock is held; the gate verifies `--is-shallow-repository=false` after refresh and fails closed otherwise;
2. checks the approved protocol blob hashes;
3. proves the source path still resolves to the expected full blob SHA;
4. reads source metadata (`action_required`, `reply_required`);
5. scans this direction's completion markers by body identity (`message_id` or exact path+blob), supporting v3 short filenames and legacy markers;
6. reads the latest matching STATUS row;
7. returns only one of:
   - `REMOTE_COMPLETED`: matching terminal completion exists;
   - `NON_REQUEST`: source explicitly says `action_required: false`;
   - `ACTIONABLE`: no authoritative terminal evidence was found.

The action-gate cache is part of the correctness boundary and must not share shallow state with the observer cache. `token-action-gate.lock` serializes init/fetch/read for that dedicated cache. The observer may remain shallow and may fetch concurrently; it cannot mutate the action gate's `shallow` state because there is no shared bare repository.

If a supposedly actionable source has a terminal STATUS row but no matching completion, the gate treats it as ambiguous and fails closed. This is intentional: it prevents a premature sender-side STATUS row from silently suppressing work, while also preventing duplicate execution when a receiver crashed between STATUS/completion operations. An operator/reconciliation path must repair that ambiguous state from evidence.

Malformed completion JSON, conflicting completion identities/statuses, protocol drift, source replacement, missing STATUS, fetch failure, inability to converge the action-gate cache to non-shallow, or oversized authoritative data all fail closed.

### `queue.EventQueue` additions

- `peek_due()` reads the oldest due local event without changing lease/attempt state.
- `claim_specific()` claims only the exact event version that passed the remote pre-claim gate.
- `owned_event()` revalidates the local owner/epoch/TTL.
- `release_claim(..., refund_attempt=True)` returns an event to `PENDING` after remote-read uncertainty without consuming the business retry budget.
- `reconcile_remote()` / `reconcile_owned_remote()` close local stale cache states as `REMOTE_COMPLETED` or `NON_REQUEST` using durable gate evidence.

### `dispatcher.ActionDispatcher`

`claim_next_actionable()` performs:

```text
peek local due event (no mutation)
  -> fresh remote gate
     -> terminal/no-action: reconcile local cache, continue
     -> actionable: exact local claim
        -> fresh remote gate again (TOCTOU close)
           -> terminal: reconcile + stop
           -> actionable: return DispatchTicket
```

`permit(ticket, boundary)` performs another remote gate while proving the local epoch is still owned. Supported boundaries are:

- `remote-message-claim`
- `wake-agent`
- `model-request`
- `business-write`

A returned `BoundaryPermit` is evidence that remote completion/STATUS was freshly checked for that source identity. It is **not** a message lease or resource lease.

## Required host wiring

The production adapter remains responsible for the current Git protocol. Use a dedicated action-gate bare repository (for example `/home/ubuntu/.hermes/token-control/action-gate-cache.git`) and keep it separate from the shadow observer's cache. The mandatory order is:

```text
1. Stage-1 source scanner inserts immutable source identity into local queue.
2. ActionDispatcher.claim_next_actionable() returns a DispatchTicket.
3. permit(ticket, "remote-message-claim").
4. Acquire/verify the actual chat message lease under LEASE_PROTOCOL v3.
5. If C/D work is needed, acquire/verify required resource lease(s) and fence tokens.
6. permit(ticket, "wake-agent") immediately before starting the business agent, if an agent is needed.
7. permit(ticket, "model-request") immediately before every physical model/provider request made for this event.
8. permit(ticket, "business-write") immediately before each externally visible business mutation; then revalidate the actual message/resource leases/fences required by that mutation.
9. Perform normal business verification and remote reply/completion/STATUS sequence.
10. Read the remote completion/reply back and only then call EventQueue.finish_local().
```

If a permit fails, returns terminal, or the local/message/resource lease is lost, do not continue from in-memory state. Reconcile authoritative state and only fill missing steps.

The adapter must not cache a permit across multiple action boundaries. A permit is an observation, not a long-lived authorization token.

## Production mutation contract

For official Hermes cron mutation, use the official CLI path that shares Hermes' jobs lock. The host-side production adapter must still implement semantic preconditions rather than byte-equality CAS on `jobs.json`:

1. read official CLI inventory immediately before mutation;
2. compute a fingerprint only from stable semantic fields for every non-target job;
3. allow volatile scheduler fields (`next_run_at`, last-run timestamps, run counters, mtimes) to advance;
4. abort and re-inventory if any non-target stable field changes;
5. snapshot raw bytes separately as forensic evidence (`0600`, fsync, read-back hash), not as the normal rollback mechanism;
6. execute one official CLI mutation;
7. read back through official CLI and raw file, prove target state and invariant non-target stable fields;
8. rollback with the official inverse mutation on failure; raw whole-file restore is reserved for an explicitly quiesced maintenance path.

This separates semantic concurrency control from forensic byte evidence and avoids fighting legitimate scheduler hot writes.

## Acceptance gate before B1 activation

Code publication alone does not close B1. Hermes host validation must show all of the following against the exact code commit:

1. the full existing test suite plus `tests/test_action_boundary.py` passes on the production Python version;
2. the dedicated action-gate cache is non-shallow after refresh, including conversion of a deliberately shallow test cache; shadow may concurrently fetch its separate cache without changing this invariant;
3. remote completion present before local claim => zero agent/model/business action and local state reconciles without burning an attempt;
4. completion arriving after local claim but before each action boundary => subsequent action is stopped;
5. protocol drift, fetch/read failure, source blob replacement, malformed/conflicting completion => fail closed, local claim released/refunded, no cursor/seen/business progression;
6. premature terminal STATUS without matching completion => fail closed, not silently skipped and not executed;
7. every actual wake/model/business entry point is wired through `permit()` and every remote mutation still revalidates the real message/resource leases/fence;
8. the 100/100 shadow run is complete under one approved protocol snapshot;
9. one final bounded canary covers the official mutation lifecycle plus the fail-closed injection in a longer scheduler-hot-write window. Repeating hundreds of mutations is not required; the purpose is independent final evidence, not load testing.

Until those checks pass, record B1 as `PARTIAL / NOT ACTIVATED`; keep the existing production path unchanged.
