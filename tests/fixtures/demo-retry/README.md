# DEMO: retry flow (canned agent)

This folder is a **demo, not a real run**. It uses a fake agent that replays two canned patches so the
reject → diagnose → feedback → retry flow can be shown reliably:

1. `1-PLANNED-FAILURE-unsafe-eval.diff` passes the tests but uses `eval()` on purpose, so the security verifier rejects it.
2. `2-correct.diff` is a correct fix and is accepted on attempt 2.

For real runs use the "live agent" launch configurations (this is the default).
