# A1X

A1X is an execution-guided Solidity/EVM vulnerability-investigation skill suite for Codex-compatible agents. It combines semantic protocol analysis, pinned-fork execution, evidence-bound test-time scaling, recursive self-aggregation (RSA), focused fuzzing and solving, replay, impact extension, and mechanically blind review.

Use A1X only on contracts and environments you are authorized to test. The workflow is designed around local or isolated historical forks, not live-chain exploitation.

## Included skills

- `a1x` — compatibility entry point
- `a1x-hunt` — end-to-end coordinator
- `a1x-runtime` — event-sourced campaign runtime and MCP server
- `a1x-recon` — deployed-state and dependency reconstruction
- `a1x-obligations` — protocol obligations and security oracles
- `a1x-compose` — multi-actor and multi-step attack composition
- `a1x-execute` — controlled execution and evidence capture
- `a1x-fuzz` — capability-aware fuzzing workflows
- `a1x-solve` — numeric, symbolic, and boundary search
- `a1x-scale` — test-time scaling and RSA search
- `a1x-validate` — replay, controls, impact, and review

The runtime version in this repository is `4.3.0`.

## Install the skills

Copy all skill packages into the shared agent skill directory:

```bash
mkdir -p "$HOME/.agents/skills"
for skill in \
  a1x a1x-compose a1x-execute a1x-fuzz a1x-hunt a1x-obligations \
  a1x-recon a1x-runtime a1x-scale a1x-solve a1x-validate
do
  cp -a "$skill" "$HOME/.agents/skills/$skill"
done
```

Invoke the suite with `$a1x`. The compatibility entry point routes full investigations through `$a1x-hunt`; it does not bypass the runtime controller.

## Campaign MCP

The local stdio MCP server exposes campaign inspection, event-chain verification, capability inspection, typed-evidence verification, experiment routing, RSA graph construction, and host-side explorer retrieval:

```bash
/bin/bash -ic 'exec "$HOME/.agents/skills/a1x-runtime/scripts/a1x" mcp stdio'
```

Example Claude Code registration:

```bash
claude mcp add --scope user --transport stdio a1x-campaign -- \
  /bin/bash -ic 'exec "$HOME/.agents/skills/a1x-runtime/scripts/a1x" mcp stdio'
```

For other MCP clients, register the same command as a local stdio server named `a1x-campaign`. A login shell lets the trusted host coordinator access operator-configured RPC variable names while the A1X fork plane keeps upstream credentials out of isolated investigation lanes.

## Runtime checks

```bash
A1X_CLI="$PWD/a1x-runtime/scripts/a1x"
"$A1X_CLI" --version
"$A1X_CLI" doctor
PYTHONPATH="$PWD/a1x-runtime/scripts" \
  python3 -m unittest discover -s a1x-runtime/tests -v
```

See each package's `SKILL.md` and `references/` directory for its operative instructions. Runtime schemas live under `a1x-runtime/scripts/schemas/`.
