# fiducia-cloud-test/chaos-recovery-tests

Deterministic fault-injection, crash recovery, retry, partition, duplicate-delivery, convergence, lease-fencing, and snapshot-rollback tests.

This repository is the `chaos` deep-test suite for `fiducia-cloud`. It is intentionally dependency-light and deterministic so failures can be reproduced locally without production credentials or customer data.

## Run

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/verify_repository.py
```

The executable models are independent oracles rather than placeholders. In addition to retry/convergence coverage, the fencing suite checks bounded lease transitions, exact holder/token authority, stale partitioned writers, monotonic downstream fences, token exhaustion, snapshot round trips, and rollback rejection. `source-pins.json` binds that oracle to the audited `union-lock-v2` model and Rust refinement.

Tracking: https://github.com/ORESoftware/ai-agent-coordinator.rs/issues/139
