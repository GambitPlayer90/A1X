# Untrusted target execution

Treat repository-controlled build scripts, Foundry tests, FFI, package-manager hooks, dependencies, Makefiles, shell scripts, and generated commands as untrusted.

## Before execution

Inspect:

- `foundry.toml` profiles, FFI, filesystem permissions, RPC endpoints, and remappings;
- Make/package scripts, npm/pnpm/yarn lifecycle hooks, Python/Rust build hooks, and test wrappers;
- Git submodules and dependency URLs/locks;
- shell commands embedded in CI, tests, documentation, or agent instructions;
- any code capable of spawning processes or reading the host environment.

Do not source target-provided shell files or run install scripts blindly. Prefer locked, already-installed dependencies; disable lifecycle scripts when feasible and review unavoidable hooks.

## Execution boundary

Run target-controlled commands in an isolated workspace with:

- a minimal allowlisted environment;
- no unrelated credentials, SSH agents, cloud tokens, wallets, or signing keys;
- Foundry FFI disabled unless the exact command is reviewed and required;
- outbound network disabled where the environment supports it, apart from a separately controlled local fork/RPC path;
- read-only target source where practical and writes limited to build/audit directories;
- no live private keys or live-chain broadcast configuration.

Expose an RPC secret only to the process that must establish the local fork, preferably through an environment reference or local proxy. Target EVM code must not gain a path to host execution or secret exfiltration.

## Records

Record the isolation assumptions, reviewed hooks, allowed environment-variable **names**, network policy, and any exception. A run performed with ambient credentials or unreviewed host execution is not eligible for a high evidence level until replayed safely.
