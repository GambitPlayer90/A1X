# A1X runtime command guide

## Table of contents

- Doctor and campaign
- Typed evidence, recon, and backend capabilities
- Obligations and hypotheses
- Sealed execution
- Fork lifecycle
- Replay and validation
- Population scaling

Set `A1X_CLI` to this skill's absolute `scripts/a1x` path and `A1X_ROOT` to the campaign directory. Every command returns JSON on stdout and a structured error on stderr.

## Doctor and campaign

```bash
"$A1X_CLI" doctor
"$A1X_CLI" campaign init \
  --root "$A1X_ROOT" --label protocol-mainnet \
  --source /absolute/target/repo --target 0xTarget \
  --chain-id 1 --block 12345678 --rpc-env MAINNET_RPC_URL \
  --authorization "Authorized local fork testing" \
  --max-runs 500 --max-scale-lanes 96 --max-parallel 4
"$A1X_CLI" campaign show --root "$A1X_ROOT"
```

`doctor` reports core readiness separately from optional backend capabilities without reading environment-variable values. It also executes a credential-free Bubblewrap namespace preflight. If `codex_lane_sandbox_ready` is false, real population rounds are recorded as `environment-blocked` before any worker starts. Campaign initialization creates a mandatory four-lane bootstrap round; run and aggregate the returned round ID. Use `campaign migrate` explicitly for a v3 campaign and `campaign verify-events` to verify the v4 hash chain.

## Typed evidence, recon, and backend capabilities

```bash
"$A1X_CLI" capability probe --root "$A1X_ROOT"
"$A1X_CLI" artifact add --root "$A1X_ROOT" --file trace.json \
  --media-type application/json --role execution-trace --producer foundry
"$A1X_CLI" evidence add --root "$A1X_ROOT" --json evidence-bundle.json
"$A1X_CLI" recon create --root "$A1X_ROOT" --facts recon-facts.json \
  --unknowns recon-unknowns.json --artifact ART-0001
"$A1X_CLI" operation propose --root "$A1X_ROOT" --blocker reachability \
  --question "Can the callback state be reached?" --backend foundry \
  --expected-information "trace to the guarded consumer" --idempotency-key HYP-0001/reachability/1 \
  --budget-json budget.json
```

Generated recon remains outside the source tree. EvidenceBundle JSON separates observation from interpretation and records target hash, backend/version, budget, execution context, and immutable artifact IDs. Use `rsa graph` to plan cross-backend composition.

## Obligations and hypotheses

```bash
"$A1X_CLI" obligation add --root "$A1X_ROOT" \
  --title "Claims remain backed" \
  --statement "Outstanding redeemable claims do not exceed realizable backing" \
  --boundary "after every public lifecycle transition" --units "asset base units" \
  --oracle "claims <= realizable backing"

"$A1X_CLI" hypothesis add --root "$A1X_ROOT" --obligation OBL-0001 \
  --mechanism "a cancellation writer leaves a claim valid after releasing backing" \
  --sequence "deposit -> request -> cancel -> redeem" \
  --support-prediction "redeem transfers value while backing reservation is absent" \
  --refute-prediction "cancel invalidates the claim or redeem restores the reservation" \
  --next-action "execute the shortest deterministic sequence"
```

## Sealed execution

Declare inputs relative to the chosen working directory or by absolute path within the source/campaign roots.

```bash
"$A1X_CLI" run plan --root "$A1X_ROOT" --hypothesis HYP-0001 \
  --class candidate --cwd /absolute/target/repo \
  --input test/A1X.t.sol --input foundry.toml \
  --property "redeemable claims remain backed" \
  --support-prediction "the assertion fails after the composed sequence" \
  --refute-prediction "the sequence reverts or the assertion holds" \
  --success-regex '1 passed' -- forge test --match-test test_A1X -vvv

"$A1X_CLI" run execute --root "$A1X_ROOT" --run RUN-0001
"$A1X_CLI" run observe --root "$A1X_ROOT" --run RUN-0001 \
  --outcome supports --property-violated yes \
  --observation "The final redeem succeeded and claims exceeded backing by X" \
  --impact "X asset units became unbacked" \
  --metric "unbacked_claims=1000000:USDC-base-units" \
  --metric "attacker_net=1000000:USDC-base-units" \
  --limitations "Local mechanism demonstration; deployment configuration pending"

"$A1X_CLI" run plan --root "$A1X_ROOT" --hypothesis HYP-0001 \
  --class control --control-for RUN-0001 --control-change 3 \
  --control-claim "remove the stale-writer transition while preserving setup and settlement" \
  --cwd /absolute/target/repo \
  --input test/A1X.t.sol --input foundry.toml \
  --property "redeemable claims remain backed" \
  --support-prediction "the control assertion holds" \
  --refute-prediction "the same backing violation remains" \
  --success-regex '1 passed' -- forge test --match-test test_A1X_control -vvv
```

`--control-change` uses a zero-based index into the command after `--`. The runtime rejects executable replacement, opaque inline-program replacement, input/fork/environment drift, undeclared argv changes, and more than four changed selector/parameter arguments.

Use `--class repair` for compilation/harness repairs, `fuzz` for a whole campaign, and `solve` for a bounded solver job. Internal fuzzer executions are not individual candidate attempts.

Record exact integer or decimal measurements with repeatable `--metric name=value:unit`. Keep gross extraction, attacker net, victim/protocol loss, liabilities, fees, and residual positions separate. Do not normalize across assets without a pinned, justified price source.

To supply an RPC URL as one argument, place `@env:MAINNET_RPC_URL` in the command. To expose a non-argument variable, use `--pass-env NAME`. `--inherit-env` is an explicit trust exception and should be rare.

## Fork lifecycle

```bash
"$A1X_CLI" fork start --root "$A1X_ROOT"
"$A1X_CLI" fork status --root "$A1X_ROOT" --fork FORK-0001
"$A1X_CLI" fork snapshot --root "$A1X_ROOT" --fork FORK-0001
"$A1X_CLI" fork revert --root "$A1X_ROOT" --fork FORK-0001
"$A1X_CLI" fork stop --root "$A1X_ROOT" --fork FORK-0001
```

The returned endpoint is loopback-only. Pass it to runs explicitly. A fork supervisor redacts the upstream RPC URL from Anvil logs and preserves a PID-start-time fingerprint to avoid signalling a reused PID.

The upstream prestate boundary is strict: dynamic tags resolve to the campaign block, explicit later block numbers fail, and transaction/receipt/trace or block-hash queries are rejected when they resolve after the pin. During blind historical evaluation, pin before the withheld incident and never use an incident transaction hash as an input.

The supervisor does not place the upstream URL in Anvil's argv. It runs a host-side pinned caching proxy and exposes a filtered UDS at the returned `socket` path. Inside a scale lane, use:

```bash
a1x-lane-fork exec -- cast block-number --rpc-url @fork
a1x-lane-fork exec -- forge test --fork-url @fork -vvv
a1x-lane-fork rpc evm_snapshot '[]'
```

`@fork` is an exact argument token, not shell interpolation. The wrapper creates the HTTP bridge only for the child command. `anvil_reset`, `hardhat_reset`, `anvil_setRpcUrl`, and node metadata are unavailable through the lane relay.

## Host-side verified-source retrieval

```bash
"$A1X_CLI" explorer retrieve --root "$A1X_ROOT" \
  --address 0x1111111111111111111111111111111111111111 \
  --campaign-epoch 1 \
  --idempotency-key "etherscan:1:0x1111111111111111111111111111111111111111"
```

The API key remains in the coordinator process. The response is content-addressed, linked into a new Recon Pack, and marked provider-observed/unpinned. Resolve proxy implementations independently at the campaign block.

## Replay and validation

```bash
"$A1X_CLI" replay prepare --root "$A1X_ROOT" --run RUN-0001 \
  --destination /absolute/clean/worktree
"$A1X_CLI" replay verify --root "$A1X_ROOT" --run RUN-0001 \
  --workspace /absolute/clean/worktree

"$A1X_CLI" candidate create --root "$A1X_ROOT" \
  --hypothesis HYP-0001 --support-run RUN-0001 --control-run RUN-0002 \
  --replay REPLAY-0001 --root-cause "..." \
  --code-evidence "writer/guard/consumer file and line references" \
  --reachability "actor, capital, ordering, time, and prerequisite justification" \
  --property "..." --impact "..." \
  --consequence-class authorization --terminal-impact no \
  --implementation-verified --configuration-verified --actor-verified --economics-verified

"$A1X_CLI" review prepare-blind --root "$A1X_ROOT" --candidate CAND-0001
"$A1X_CLI" review execute-blind --root "$A1X_ROOT" --review BLIND-0001 -- \
  reviewer-command --packet '{packet}' --output '{output}'
"$A1X_CLI" candidate gate --root "$A1X_ROOT" --candidate CAND-0001
"$A1X_CLI" candidate promote --root "$A1X_ROOT" --candidate CAND-0001
```

A v4 E6 review runs in a fresh process from a sealed minimal packet with investigator rationale withheld. Its JSON output must contain `verdict`, Boolean `reproduced`, and a `challenges` array. A manually declared independent review remains commentary and cannot satisfy E6. A requested `rejected` verdict also requires typed `--evidence-ref` arguments. Without a mechanism-specific negative run or an anchored impossibility proof, the runtime records `needs-work` and keeps the candidate alive.

Candidate creation also creates a mandatory four-lane expansion round. Run it even when the current authorization or accounting consequence is already valid.

`replay prepare` creates an isolated replay container with `source/` and `campaign/` roots. It clones the source at the pinned commit when Git identity exists, otherwise makes a filtered source copy, then materializes every declared source- or campaign-anchored input under the matching replay root. Campaign-side harnesses are never executed from the original campaign directory. Replay verifies the commit, declared input hashes, mapped working directory, exit behavior, and optional success regex. It is intentionally not a semantic theorem.

## Population scaling

```bash
"$A1X_CLI" scale create --root "$A1X_ROOT" --prompt-file lane-task.md \
  --hypothesis HYP-0001 \
  --axis "lifecycle interruption" --axis "alternate actor/callback" \
  --axis "numeric boundary" --axis "strongest intended-behavior refutation"

"$A1X_CLI" scale run --root "$A1X_ROOT" --round ROUND-0001 --parallel 4 --lane-forks auto --cyber-access-program standard
"$A1X_CLI" scale aggregate --root "$A1X_ROOT" --round ROUND-0001
"$A1X_CLI" scale auto-select --root "$A1X_ROOT" --round ROUND-0001 --maximum 6
"$A1X_CLI" scale select --root "$A1X_ROOT" --round ROUND-0001 \
  --select LANE-0001 --select LANE-0003 \
  --reserve LANE-0004 \
  --rationale "distinct mechanisms with the strongest executed evidence" \
  --drop "LANE-0002:exact artifact-bound duplicate of LANE-0001"
"$A1X_CLI" scale evolve --root "$A1X_ROOT" --parent-round ROUND-0001 \
  --generations 3 --children 3 --closure-lanes 1 --fresh-lanes 1 --stagnation-rounds 2 --parallel 4 \
  --lane-forks auto
```

Omit `--model` and `--reasoning` to use the signed-in Codex defaults. `--cyber-access-program standard` is the default and explicitly identifies the authorized defensive research tier to Codex; select `daybreak_blue` or `daybreak_red` only when the signed-in account has that program. Selecting a value does not grant access. `--closure-lanes` reserves child slots for single-parent witness closure before pairwise RSA. `--lane-forks auto` allocates a credential-free writable fork when the pinned campaign chain and host RPC variable are available; `require` fails closed and `off` disables allocation. The coordinator probes direct RPC, the HTTP bridge, and MCP before starting the lane and records `.a1x/fork-transport.json`. Inside a lane, use `a1x-lane-fork rpc` for direct calls and `exec ... @fork` for Forge/Cast when `http_bridge.ready` is true. API-key environment variables are removed from lane processes unless `--allow-env-auth` is explicitly set. Lanes use writable temporary home/state directories and mode-restricted temporary copies of the minimum Codex credential/config state. Worker writes cannot modify the operator originals. Lanes run ephemerally without unrelated user rules.

Every accepted handoff names the tested obligation, the discriminator, and a writer/guard/consumer/state/property causal identity. Safe deduplication additionally requires exact attacker-model and reached-state-shape anchors plus the ordered transition sequence. Missing or coarse identity remains unique. Its evidence paths must resolve inside the lane. Runtime-derived artifact hashes and causal keys—not narrative wording—control evidence fitness and deduplication.

Manual selection cannot erase a distinct lead: omitted candidate/near-miss lanes enter the reserve automatically. `--drop` is accepted only when the runtime can match the lane to a retained exact artifact-bound duplicate.

## Impact and completion

```bash
"$A1X_CLI" frontier add --root "$A1X_ROOT" --kind downstream-consumer \
  --statement "captured authority may reach an asset allocator" \
  --evidence-ref '{"type":"source-anchor","anchor":"source","path":"src/Controller.sol","line_start":90,"line_end":120}' \
  --next-action "execute the shortest allocator call" --priority high --cost low \
  --candidate CAND-0001

"$A1X_CLI" impact add --root "$A1X_ROOT" --candidate CAND-0001 \
  --capability "callback can mutate settlement configuration" --sink "escrow release" \
  --consequence "reserved assets may be released to an unintended receiver" \
  --impact-property "escrow releases cannot exceed obligations backed for the receiver" --status open \
  --evidence-ref '{"type":"source-anchor","anchor":"source","path":"src/Settlement.sol","line_start":40,"line_end":88}' \
  --next-action "execute settlement after the callback mutation" \
  --high-consequence --low-cost

# RUN-0001 is CAND-0001's original support run. RUN-0012 is a new experiment
# that carries that primitive into the registered downstream sink.
"$A1X_CLI" run plan --root "$A1X_ROOT" --hypothesis HYP-0001 \
  --class candidate --extends-candidate CAND-0001 --extends-run RUN-0001 \
  --extension-prefix test/A1XImpact.t.sol --cwd /absolute/target/repo \
  --input test/A1XImpact.t.sol --input foundry.toml \
  --property "escrow releases cannot exceed obligations backed for the receiver" \
  --support-prediction "the authority primitive reaches release and violates backing" \
  --refute-prediction "release remains bounded or the composed prefix is unreachable" \
  --success-regex '1 passed' -- forge test --match-test test_A1XImpact -vvv

# Plan RUN-0013 as the causal control for downstream RUN-0012, not RUN-0001.
"$A1X_CLI" run plan --root "$A1X_ROOT" --hypothesis HYP-0001 \
  --class control --control-for RUN-0012 --control-change 3 \
  --control-claim "remove the downstream release transition while preserving acquired authority" \
  --cwd /absolute/target/repo --input test/A1XImpact.t.sol --input foundry.toml \
  --property "escrow releases cannot exceed obligations backed for the receiver" \
  --support-prediction "the control preserves backing" \
  --refute-prediction "the release violation remains" \
  --success-regex '1 passed' -- forge test --match-test test_A1XImpact_control -vvv

"$A1X_CLI" impact resolve --root "$A1X_ROOT" --impact IMPACT-0001 \
  --status demonstrated \
  --evidence-ref '{"type":"run-receipt","run_id":"RUN-0012","outcome":"supports"}' \
  --evidence-ref '{"type":"replay","replay_id":"REPLAY-0004"}' \
  --evidence-ref '{"type":"run-receipt","run_id":"RUN-0013","outcome":"refutes"}'

for family in value authority lifecycle numeric composition; do
  "$A1X_CLI" coverage record --root "$A1X_ROOT" --family "$family" \
    --status challenged \
    --evidence-ref '{"type":"source-anchor","anchor":"source","path":"src/Settlement.sol","line_start":1,"line_end":120}' \
    --limitations "state range and actor bounds actually tested"
done

"$A1X_CLI" controller assess --root "$A1X_ROOT"
"$A1X_CLI" controller close --root "$A1X_ROOT" --closure clean \
  --conclusion "Evidence-backed campaign conclusion"
```

Accepted evidence-reference types are `run-receipt`, `replay`, `fork-snapshot`, `source-anchor`, `trace-artifact`, `state-diff`, `deployment-observation`, and `solver-witness`. Artifact-backed types resolve and hash the referenced object immediately. A high-consequence demonstration requires a new downstream support run planned with `--extends-candidate`, the candidate's original `--extends-run`, and a declared `--extension-prefix`. The runtime seals the parent plan/receipt hashes, candidate relation, prefix digest, and chain/block identity. That downstream run must violate the exact registered property and replay successfully. A distinct `control` run then uses `--control-for` against the downstream run, one to four exact `--control-change INDEX` values, and a non-empty `--control-claim`; it preserves the downstream harness, inputs, fork, environment, executable and argv shape, includes a trace/state diff, and preserves the property. High-consequence refutation likewise uses an extension-linked negative run for the exact property and hypothesis, or an extension-linked deployment/solver proof plus source grounding. Missing promotion evidence leaves the branch open; it never deletes the lead.

For a blocked branch, add `--blocker-kind budget|environment|external-prerequisite|tooling` and a non-empty `--resolution-condition`. Adding a grounded high-priority frontier with low or medium test cost automatically creates direct-discriminator, alternate-branch, and strongest-refutation lanes. Allocation failure preserves the frontier/candidate and records the failure; it never erases the research record.

The close command fails when mandatory TTS, candidate extension, impact propagation, RSA, coverage, or cheap-frontier work remains. When only evidenced blockers remain, select the matching explicit closure: `budget-exhausted`, `environment-blocked`, or `open-risk`. A `clean` close succeeds only for `READY_CLEAN`.
