# Gate 1 preparation (prepared 2026-10-16; NOT advanced: status stays in-progress)

Gate 1 = after F001-F006 are accepted and the deterministic suite is green (F002 was removed at Gate 0).

| Feature | State | Evidence |
|---|---|---|
| F001 registry + doctor | accepted (night 1) | run f1824d4b-2683-4410-974c-383c5f13012e |
| F003 observed model/usage in receipts | accepted 2026-10-16 | run 86a9c529-95d9-42b3-9e23-b24c18fec0ff |
| F004 fleet v2 | **accepted 2026-10-16 (owner approved)** | run 35ecb39a-5c22-4108-acef-41f7fc694ad6 (T-046), record sha256 64e8240bde0c6b62f682024a2c4f7ac56b8e433abdbc9d73d23dcd6d68d16268 |
| F005 ledger v1 | accepted 2026-10-16 with the first fold | run fdf5dd38-1433-45eb-972b-823493f9e671 |
| F006 structured verdicts | accepted 2026-10-16 | run db01ac53-00de-4d30-9230-05894b952ebe |

Deterministic suite on HEAD fa61b50: `bash tests/run-tests.sh` exit 0 ("ALL TESTS PASSED"); `verify-mission.sh --require-workers` VERIFY OK.

## Commands, in order (you run them; I did not)

1. Accept F004:
   `bash scripts/accept-feature.sh --run-id 35ecb39a-5c22-4108-acef-41f7fc694ad6 --verification-sha256 64e8240bde0c6b62f682024a2c4f7ac56b8e433abdbc9d73d23dcd6d68d16268 --accepted-by "<identity>" docs/missions/20261014-2a-foundation`
   then `bash scripts/verify-mission.sh --require-workers docs/missions/20261014-2a-foundation` (recompute the sha256 of the record right before, as for F006).
2. Gate 1: `bash scripts/verify-mission.sh docs/missions/20261014-2a-foundation` must exit 0; set `status: awaiting-gate` in GOAL.md; you give the verdict; append a "Human - GATE 1" entry (the Front Desk records it from your words); status back to `in-progress` (or `done`).

## Not part of Gate 1 (Gate 2)

F007: real smoke ran 2026-10-16 (exit 0, 4 workers + 1 brain, evidence `evidence/F007-smoke.md`, record run f544e83c-6189-4e96-80a6-677224ef1dfa sha256 3cca09afa0dfd58ea69cc305fd6ad4e6690aadfd80b1b4b81cc8dd0d216b7624). Open: step 2 vs Codex (observed model unknown).


## Update 2026-10-16 (day 4): F004 accepted; the F004 step 'chair seat resolves to agy' was removed by the agy amendment and agy is now coming back as F009 (owner, day 4). Gate 1 itself is not advanced.
