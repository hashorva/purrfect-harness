# F007 real-provider smoke evidence

This directory is a self-contained archive of the accepted disposable-consumer
smoke run. It preserves the four separate Phase 1 truths without relying on chat
history or the original `/private/tmp` repository:

1. `consumer/execution-spec.json`, `consumer/fleet.json`, and `consumer/T-001.md`
   record what was authorized.
2. `consumer/execution-receipt.json`, `consumer/worker.log.sanitized`,
   `consumer/nonce.txt`, and `consumer/consumer-history.bundle` record what ran
   and what Git-visible change actually occurred.
3. `consumer/verification-record.json` records which committed checks passed.
4. `consumer/features.json` records the orchestrator's separate acceptance of
   that exact run and VerificationRecord hash.

`manifest.json` hashes every evidence input. From any fresh shell with Python 3
and Git installed, run:

```bash
python3 reconstruct.py
```

The checker reads only files in this archive, verifies their hashes and linked
identities, clones the archived Git bundle into a temporary directory, and emits
a compact JSON reconstruction. A zero exit and `"result": "PASS"` are the Gate 2
machine-checkable proof.

