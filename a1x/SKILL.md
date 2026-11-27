---
name: a1x
description: Compatibility entry point for the A1X execution-guided Solidity/EVM vulnerability investigation. Use when the user invokes $a1x or requests the established A1X workflow; route the complete authorized hunt through $a1x-hunt and its runtime-enforced scaling, impact, replay, and completion controls.
---

# Route legacy A1X invocations safely

Invoke `$a1x-hunt` and follow its complete workflow. Do not reproduce an older coordinator from memory and do not bypass the V4 event-sourced runtime controller.

If `$a1x-hunt` is unavailable, stop and report that the compatibility entry point cannot locate the canonical coordinator. Do not fall back to an installed legacy workflow.
