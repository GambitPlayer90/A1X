# V5 command guide

Set task-specific paths after locating the runtime skill from the skills catalog:

```bash
A1X_CLI=/absolute/path/to/a1x-runtime/scripts/a1x
A1X_ROOT=/absolute/path/to/audit-work/campaign
```

The CLI never invokes a model process. Known model executables and opaque inline interpreter programs are rejected at the sealed-run boundary; use reviewable harness/script files for deterministic tools and the current Codex chat for built-in subagents.

## Initialize and recover context

```bash
"$A1X_CLI" doctor
"$A1X_CLI" campaign init \
  --root "$A1X_ROOT" --label target-mainnet --source /absolute/target \
  --target protocol-name --chain-id 1 --block 12345678 \
  --block-hash 0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --rpc-env MAINNET_RPC_URL --authorization 'authorized bug-bounty assessment'
"$A1X_CLI" ledger brief --root "$A1X_ROOT"
"$A1X_CLI" ledger verify --root "$A1X_ROOT" --repair-views
```

Resolve the canonical block hash before initialization. Initialization creates records only. It starts no Anvil, worker, or Codex process. `fork start` refuses a different observed hash.

For a V4 campaign:

```bash
"$A1X_CLI" ledger migrate-v4 --root "$A1X_ROOT"
"$A1X_CLI" ledger migrate-v4 --root "$A1X_ROOT" --apply
```

The first command previews. Apply creates only `v5/` sidecar state and never rewrites legacy artifacts.

## Ledger

Create exact scope first:

```bash
"$A1X_CLI" ledger add --root "$A1X_ROOT" --kind SCOPE \
  --title 'Program scope and eligible impacts' \
  --statement 'Exact deployed target and unprivileged attacker boundary' \
  --priority critical --status active \
  --data '{"impacts":["direct theft of user funds"],"exclusions":[],"attacker":"fresh unprivileged contract","cost":"low"}'
```

Add `OBL`, `INV`, `EXP`, `FACT`, `TASK`, and `SYN` the same way. `TASK.data.question` is required. A `SYN` parents its `INV` and supplies existing `inputs`, `grounded_delta`, `revised_attempt`, `next_discriminator`, and `follow_through`. Completed/refuted synthesis records an outcome and resulting `EXP` or artifact; deferral records an exact reason.

```bash
"$A1X_CLI" ledger add --root "$A1X_ROOT" --kind SYN \
  --title 'callback-bound consumer substitution' \
  --statement 'combine the reachable callback and exact numerical bound' \
  --parent INV-0001 --parent FACT-0002 --scope SCOPE-0001 \
  --priority high --status open --next-action 'execute the revised discriminator' \
  --data '{"investigation_id":"INV-0001","inputs":["FACT-0002"],"grounded_delta":"the callback reaches the bound before settlement","revised_attempt":"invoke the alternate consumer before settlement","next_discriminator":"compare backing before and after settlement","follow_through":"pending","cost":"low"}'
```

```bash
"$A1X_CLI" ledger list --root "$A1X_ROOT" --kind INV --status open
"$A1X_CLI" ledger show --root "$A1X_ROOT" --id INV-0001
"$A1X_CLI" ledger update --root "$A1X_ROOT" --id INV-0001 \
  --expected-revision 1 --reason 'fork experiment reached the callback waypoint' \
  --changes '{"stage":"hypothesis","status":"active","next_action":"execute the settlement discriminator"}'
```

Read the record first and use its current revision. A stale update fails closed.

## Tool and target probes

```bash
"$A1X_CLI" doctor --root "$A1X_ROOT"
"$A1X_CLI" capability probe --root "$A1X_ROOT"
```

The doctor reports tool availability without reading secret values. Target probe output controls backend routing; installed does not mean compatible.

## Recon coverage attestation

Run the bundled `$a1x` scanner and coverage gate first. The scan must use `--root` so paths are source-relative. Its JSON contains both mutation `entry_points` and `read_surfaces`; the coverage map classifies both. After the gate passes, bind immutable snapshots to the campaign:

```bash
"$A1X_CLI" recon bind-coverage --root "$A1X_ROOT" \
  --entry-points "$A1X_ROOT/recon/entry-points.json" \
  --coverage-map "$A1X_ROOT/recon/coverage-map.json" \
  --graph-summary "$A1X_ROOT/recon/graph-summary.json"
"$A1X_CLI" recon verify-coverage --root "$A1X_ROOT"
```

Omit `--graph-summary` only when Graphify is unavailable and that limitation is recorded elsewhere. Verification rechecks input seals, exact file/entry/reader reconciliation, and current hashes of every scoped Solidity file. `controller assess` refuses clean completion without a current passing attestation.

## Session-owned Anvil fork

```bash
"$A1X_CLI" fork start --root "$A1X_ROOT"
"$A1X_CLI" fork status --root "$A1X_ROOT" --fork FORK-0001
"$A1X_CLI" fork snapshot --root "$A1X_ROOT" --fork FORK-0001
"$A1X_CLI" fork revert --root "$A1X_ROOT" --fork FORK-0001 --snapshot 0x1
"$A1X_CLI" fork stop --root "$A1X_ROOT" --fork FORK-0001
```

Announce and record the returned fork ID, chain, pinned block/hash, loopback endpoint, supervisor PID, logs, base snapshot, and stop command. The upstream URL is never stored in Anvil argv or evidence. Do not share mutable fork state across concurrent experiments.

## Sealed execution

Create canonical ledger records first, then cross-link every typed runtime record. The following assumes `SCOPE-0001`, ledger `OBL-0001`, and ledger `INV-0001` already exist, and `INV-0001.scope=["SCOPE-0001"]`:

```bash
"$A1X_CLI" obligation add --root "$A1X_ROOT" \
  --ledger OBL-0001 \
  --title 'backing conservation' --statement 'claims never exceed realizable backing' \
  --boundary settlement --units wei --oracle 'independent asset/liability delta'

"$A1X_CLI" hypothesis add --root "$A1X_ROOT" --obligation OBL-0001 \
  --ledger INV-0001 \
  --mechanism 'split updates leave internal credit above backing' \
  --sequence 'prepare -> split action -> settle -> withdraw' \
  --support-prediction 'internal credit rises without matching backing' \
  --refute-prediction 'settlement reconciles every split' \
  --next-action 'run one-shot and split-action fork discriminator'

"$A1X_CLI" ledger add --root "$A1X_ROOT" --kind EXP \
  --title 'split versus one-shot settlement' \
  --statement 'execute the exact settlement discriminator' \
  --parent INV-0001 --scope SCOPE-0001 --priority high --status open \
  --next-action 'execute the sealed fork run' --data '{"cost":"low"}'

"$A1X_CLI" run plan --root "$A1X_ROOT" --ledger EXP-0001 --hypothesis HYP-0001 \
  --class candidate --cwd /absolute/harness --fork FORK-0001 \
  --property 'realizable liabilities do not exceed backing' \
  --support-prediction 'split sequence violates the property' \
  --refute-prediction 'all split sequences preserve the property' \
  -- forge test --match-test test_split_settlement -vvvv
"$A1X_CLI" run execute --root "$A1X_ROOT" --run RUN-0001
"$A1X_CLI" run observe --root "$A1X_ROOT" --run RUN-0001 \
  --outcome supports --property-violated yes \
  --observation 'internal credit exceeded realizable backing after settlement' \
  --metric backing_delta=-100:wei
```

Use `@env:NAME` only as a whole command argument. Record compilation/harness repairs as repair runs, not hypothesis support.

Every public run plan requires one canonical `EXP` parented by the hypothesis's `INV`. Planning links the sealed plan into that `EXP`; observation links the result and closes the experiment. Candidate creation refuses support/control runs without this cross-link.

## Replay and independent challenge

Prepare and verify clean replay with the replay commands exposed by CLI help. Create a candidate only after support, control, and replay records are consistent. Candidate creation and every later promotion recheck the sealed plan, receipt, observation, canonical replay, and exact `replay.run_id == candidate.support_run` binding. `candidate create` requires `--scope SCOPE-0001 --eligible-impact '<exact data.impacts string>'`; approximate category matches fail.

For the strongest independent evidence:

```bash
"$A1X_CLI" review prepare-blind --root "$A1X_ROOT" --candidate CAND-0001
# The primary chat gives the sealed packet to a visible built-in subagent.
# That subagent writes the bound schema to the returned submission_path.
"$A1X_CLI" review complete-in-session --root "$A1X_ROOT" \
  --review BLIND-0001 --subagent-thread independent_reviewer \
  --result "$A1X_ROOT/reviews/BLIND-0001/subagent-result.json" \
  --attest-visible-subagent
```

The result JSON echoes `review_id`, `candidate_id`, `packet_sha256`, `challenge_nonce`, and `subagent_thread`, and supplies `verdict`, Boolean `reproduced`, and non-empty `challenges`, `reproduction_commands`, and `artifact_refs` arrays. Qualification rechecks the packet and review-output seals and their current candidate/replay/task bindings. The runtime cannot authenticate Codex UI thread identity; the primary attests what is visible through `/subagents`. It never launches the reviewer.

## Stateful fuzzing and solving

Use `harness`, `actors`, `component`, `oracle`, `progress`, and `solver` commands only after reading their CLI help and the relevant `$a1x` tool-routing reference. A stateful harness must explicitly cover all runtime categories, including unknown/not-applicable entries. Preserve seeds, corpora, action/precondition telemetry, state fingerprints, shrink results, and deterministic replay.

## Impact and closure

Record the exact downstream impact property, support/replay/control evidence, and applicability. Use:

```bash
"$A1X_CLI" controller assess --root "$A1X_ROOT"
"$A1X_CLI" campaign verify-events --root "$A1X_ROOT"
"$A1X_CLI" ledger verify --root "$A1X_ROOT"
"$A1X_CLI" controller close --root "$A1X_ROOT" \
  --closure open-risk --conclusion 'validated candidates and disclosed unresolved paths'
```

The completion gate checks ledger/scope/impact state, sealed recon coverage, evidence, exact replay binding, bounded open work including synthesis, and process cleanup. V5 has no lanes, populations, or RSA generations. Stop all recorded Anvil/fuzzer processes before closure.
