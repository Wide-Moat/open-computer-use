# 13 — anthropic-experimental/sandbox-runtime (local Claude Code sandbox)

> Source: [`references/sandbox-runtime/`](../../../references/sandbox-runtime/). **Not** `process_api` (which is closed and uses Firecracker). This is the local-machine sandbox: bubblewrap on Linux, seatbelt on macOS, seccomp BPF.
> Relevant as **secondary defense inside our microVMs** (Phase 9) and as patterns for our agent tool execution (Phase 7).

## 1. Filesystem allowlist — deny-then-allow reads, allow-only writes

- **Where.** macOS: `src/sandbox/macos-sandbox-utils.ts:generateReadRules()` (lines 237–260). Linux: `src/sandbox/linux-sandbox-utils.ts` (bind-mount pattern, lines 145–159).
- **What.**
  - **Reads:** start permissive, broad denials (`/Users`), re-allow narrow areas (`.`). Later rules override → asymmetric precedence.
  - **Writes:** allow-only — nothing writable by default; must explicitly allow paths.
  - Linux uses `--ro-bind /blocked /blocked` (read-only mount) and `--bind /allowed /allowed` (read-write); for non-existent deny paths, mounts `/dev/null` at first missing component to block directory creation.
- **Why for us.** Phase 7 tool execution and Phase 9 inside-microVM secondary defense. Asymmetric precedence is unintuitive but **safer than symmetric** — document loudly when adopted.

## 2. Mandatory deny paths — secondary always-on safety

- **Where.** `src/sandbox/sandbox-utils.ts:DANGEROUS_FILES` (11–21), `getDangerousDirectories()` (34–40). macOS: `:47-74`. Linux: `:166-284`.
- **What.** Unconditionally blocked from writes regardless of config:
  - Files: `.gitconfig`, `.gitmodules`, `.bashrc`, `.bash_profile`, `.zshrc`, `.zprofile`, `.profile`, `.ripgreprc`, `.mcp.json`.
  - Dirs: `.git/hooks`, `.git/config` (conditional), `.vscode/`, `.idea/`, `.claude/commands`, `.claude/agents`.
- **macOS implementation.** Static glob in Seatbelt profile; blocks file moves/creation via `(deny file-write-unlink)` + `(deny file-write-create)` on ancestor dirs.
- **Linux implementation.** Single ripgrep call with multiple `--iglob`; depth-limited (default 3). Special case: `.git` as file (git worktree) → skip blocking.
- **Why for us.** Phase 7 and 8. Blocks code-execution vectors (shell config, git hooks) inside sandboxes. Prevents agent from modifying its own config.

## 3. Network isolation — proxy-mediated, deny by default

- **Where.** `src/sandbox/http-proxy.ts:createHttpProxyServer()` (line 74 onward, CONNECT handler); `:29-34` (filter callback); `:54` (per-request filter hook).
- **What.**
  - **macOS:** Seatbelt allows only `(localhost, specific-port)` → routed through HTTP / SOCKS5 proxies on host with domain allowlist.
  - **Linux:** Network namespace **completely removed** by bubblewrap (`--unshare-net`). All traffic via Unix domain sockets → `socat` bridges to host's TCP proxies. Seccomp blocks Unix socket **creation** (inherited FDs still work).
- **Threat model (README:112-127).**
  > "Without file isolation, a compromised process could exfiltrate SSH keys. Without network isolation, a process could escape the sandbox and gain unrestricted network access."
- **Why for us.** Phase 7 agent tool execution and Phase 9 inside-microVM defense-in-depth. Direct match for the agentbox-style egress pattern but at process level rather than network level. **Layer with our network-level egress proxy ([`09-agentbox.md`](./09-agentbox.md))**.

## 4. Linux seccomp BPF — Unix-socket creation block ⭐

- **Where.** Generator: `vendor/seccomp-src/seccomp-unix-block.c:51-80`. Applier: `vendor/seccomp-src/apply-seccomp.c:1-30`.
- **What.**
  ```c
  ctx = seccomp_init(SCMP_ACT_ALLOW);
  scmp_filter_add_rule(ctx, SCMP_ACT_ERRNO(EPERM),
                       SCMP_SYS(socket),
                       SCMP_A0(SCMP_CMP_EQ, AF_UNIX));
  ```
  Blocks `socket(AF_UNIX, ...)` while allowing AF_INET/INET6. Also blocks `io_uring_setup/enter/register` (which could create sockets on Linux ≥ 5.19).
- **Two-stage isolation.**
  1. `bwrap` creates FS / network sandbox (outer PID ns).
  2. `apply-seccomp` creates **nested user + PID namespace**, remounts /proc, sets `PR_SET_DUMPABLE=0`, forks, applies seccomp via `prctl(PR_SET_SECCOMP)`, execs user command.
  3. Nested ns ensures user command can't `ptrace` / read `/proc/N/mem` of unfiltered helpers.
- **Footgun.** **32-bit x86 (ia32) NOT supported** — the `socketcall()` multiplexer bypasses the filter. Supporting it requires BPF arg inspection (complex, currently incomplete).
- **Why for us.** Phase 9 inside-microVM defense. Kernel-enforced; no userspace bypass. The **two-stage nested-namespace pattern** is the takeaway — prevents process-level escapes that pure bubblewrap wouldn't catch.

## 5. macOS Seatbelt — declarative capability policy (Lisp DSL)

- **Where.** `src/sandbox/macos-sandbox-utils.ts:wrapCommandWithSandboxMacOS()`.
- **What.** Dynamically-generated Lisp policies:
  ```lisp
  (version 1)
  (allow default)
  (deny file-read* (subpath "/Users"))
  (allow file-read* (subpath "."))
  (deny network*)
  (allow network-outbound (literal "localhost") (literal 127.0.0.1:PORT))
  (allow file-write* (subpath "."))
  (deny file-write* (literal ".bashrc"))
  (deny file-write-unlink (subpath ".git"))
  ```
- **Operations:** `file-read*`, `file-write*`, `network*`, `process*`, `mach*`. **Matchers:** `literal`, `subpath`, `regex` (glob→regex).
- **Violation monitoring** — `:88-96`: log tag encodes command in base64 for correlation; macOS system logs feed Claude Code's `/var/log` reader in real time.
- **Why for us.** Out-of-scope (we're Linux-focused), but the **policy structure** (operations × matchers + violation log) is reusable as a mental model.

## 6. Symlink-attack defenses

- **Where.** Linux: `src/sandbox/linux-sandbox-utils.ts:findSymlinkInPath()` (lines 74–105). macOS: `sandbox-utils.ts:isSymlinkOutsideBoundary()` (lines 89–116).
- **What.** Walks path components, checks each for a symlink within an allowed-write boundary → blocks if found. Allows legit system symlinks (`/tmp → /private/tmp` on macOS).
- **Footgun.** Linux check only handles **existing** symlinks; new symlinks to non-existent paths can be created. Mitigation: combine with mandatory denies (§2).
- **Why for us.** Phase 9. TOCTTOU/symlink attacks bypass static path blocks. Validate symlink targets at enforcement time.

## 7. Design philosophy (Anthropic quotes)

> "Secure-by-default philosophy tailored for common developer use cases: processes start with minimal access, and you explicitly poke only the holes you need." (README:41)

> "Both filesystem and network isolation are required for effective sandboxing." (README:112-127)

**Key takeaways.**
1. **OS-level enforcement, not userspace.** Kernel-backed Seatbelt / bwrap / seccomp. Smaller TCB.
2. **Fail-closed.** Default deny; filters fail to `EPERM`, not silently passing.
3. **Defense in depth.** FS rules + network proxies + mandatory denies + nested ns + seccomp.
4. **Configuration validated** with Zod schemas — type safety on every restriction.

## 8. Anti-patterns & known limitations (must-document)

- **Overly broad `allowedDomains`** (README:654). `github.com` allows any API call to any endpoint. → Custom per-request filter or MITM + cert pinning.
- **`allowUnixSockets: ["/var/run/docker.sock"]`** ≈ full host escape (README:657). → Only allow vetted, non-IPC sockets.
- **Writes to `/bin` or `$PATH`** → RCE in other users' contexts. **Writes to `.bashrc`** → persistent shell backdoor.
- **`enableWeakerNestedSandbox`** — disables unprivileged user namespaces for DinD; substantially weakens seccomp. **CI only.**
- **`enableWeakerNetworkIsolation`** — re-enables `com.apple.trustd.agent` for Go TLS verification; opens exfil via trustd (README:350).

## Mapping to our architecture

| Anthropic pattern | Our Phase 7 (agent hardening) | Our Phase 9 (microVM defense-in-depth) |
|---|---|---|
| Dual FS + net isolation | Tool allowlists + egress proxy | Nested ns + seccomp inside VM |
| Mandatory denies | Block config/hook files | State-file anti-tampering |
| Symlink defenses | Path validation at dispatch | TOCTTOU detection |
| Deny-then-allow reads | Minimal env-var exposure | Only mounted FS visible |
| Seatbelt / bwrap | Language-level restrictions | OS-level enforcement |
| Seccomp BPF Unix-socket block | — | Block sandbox-escape via IPC |
| Two-stage nested PID ns | — | Prevents ptrace escape |

## Phase-8 adoption priorities

1. **`PR_SET_DUMPABLE=0` on agent PID 1** (matches [pattern 5 in `00`](./00-anthropic-and-sandboxd.md)).
2. **Seccomp profile** for guest agent: deny `AF_UNIX socket()`, `io_uring_*`.
3. **Mandatory deny paths** for `.git/hooks`, `.bashrc`, `.mcp.json` inside the workspace home.
4. **Symlink-target validation** in our file-write tool implementations.
5. **Document weakening flags** as **never on in prod** in our Helm values.
