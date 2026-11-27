# Causal controls and clean replay

## Causal control

Choose a control that changes only the suspected enabling mechanism:

- remove the enabling call;
- use the correctly bound actor/asset/epoch/domain;
- consume or update the missing state at the intended boundary;
- use a non-triggering neighboring amount/time;
- prevent the callback while preserving the outer action;
- replay against a relevant corrected relation when available.

The control should eliminate the property violation while leaving prerequisites and measurement comparable. Record unexpected control behavior rather than choosing a friendlier control after the fact.

For a high-consequence downstream impact, register the exact impact property. First plan a new downstream support run with `--extends-candidate CAND-####`, `--extends-run RUN-A`, and `--extension-prefix PATH`, where RUN-A is the candidate's recorded primitive-support run. The runtime seals the candidate/parent relation, parent plan and receipt, prefix digest, and chain/block identity. The downstream run (RUN-B) must test and violate the registered impact property and replay cleanly.

Then plan the downstream-specific control with `--control-for RUN-B`, `--control-change INDEX`, and `--control-claim "exact transition removed"`. The runtime requires the same harness inputs, working directory, fork, environment boundary, executable, and argv shape; only one to four declared non-program selector/parameter arguments may differ. Attach a control trace or state-diff artifact. The control removes only the suspected enabling transition and preserves the downstream property. A control for the earlier primitive RUN-A—or an unrelated negative run with the same generic property text—does not control the longer extraction or settlement path.

These structural checks prevent whole-program substitution and unpaired negative runs. They do not infer semantic causality: the independent reviewer must inspect the sealed control claim, exact argv delta, harness branch, and trace/state delta and confirm that only the alleged enabling transition changed.

## Clean replay

Use a fresh checkout/worktree or clean copied source at the same commit. Recreate dependencies from lockfiles, use the same compiler/tool configuration and pinned fork, copy only the declared harness/candidate inputs, and run the exact command. Do not copy build artifacts or mutated fork state.

Verify hashes for target sources, harness, configuration, dependency locks, and relevant fixtures. Capture tool versions, environment variable names, exit status, assertions, and logs. Keep secrets out of artifacts.

## Independence

Clean replay guards against workspace drift and hidden dependencies; it does not independently judge semantics. For E6, run `review prepare-blind` and `review execute-blind`. The runtime seals a minimal evidence packet, withholds investigator rationale, launches a fresh process, hashes its inputs/output, and records process identity. The reviewer first reproduces the behavior, then challenges causality, actor reachability, deployed applicability, and impact. A declared Boolean or same-context review cannot satisfy E6. Without this mechanical blind-review record, the evidence ceiling is E5.

## Failure

A failed replay lowers the promotion ceiling but does not refute or delete the lead. Diagnose source/config drift, nondeterminism, missing dependency, fork-state change, or fixture contamination. Never suppress the failure or relax assertions merely to recover the claim.

A reviewer rejection is held to the same asymmetric standard. Intended behavior, a persuasive guard, an ordinary-state pass, or a failed exploit harness is not enough. Require a mechanism-specific negative execution that preserves the tested property, or an artifact-bound source plus deployment/solver impossibility proof. Otherwise record `needs-work` and continue the adversarial branch.
