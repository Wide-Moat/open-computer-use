# Codebase Concerns

**Analysis Date:** 2026-04-12

## Tech Debt

**Broad Exception Handlers Swallowing Errors:**
- Issue: Extensive use of bare `except Exception: pass` throughout the codebase suppresses real errors and makes debugging difficult
- Files: `computer-use-server/app.py` (lines 689-690, 701-702, 706-707, 718-722, 742-743, 759-760), `computer-use-server/mcp_tools.py` (lines 259-260, 432, 959, 986-987, 1002-1003, 1023-1024, 1058-1059)
- Impact: Silent failures in critical paths (WebSocket forwarding, terminal handling, Docker operations) make production issues nearly impossible to diagnose without adding logging
- Fix approach: Replace bare `except` with specific exception types and log at WARNING/ERROR level. Consider structured logging with context (chat_id, container_name) for traceability

**MCP SDK Bug Workaround - Progress Reporting:**
- Issue: MCP SDK's `ctx.report_progress()` doesn't pass `related_request_id` in stateless HTTP mode, causing progress notifications to get lost
- Files: `computer-use-server/mcp_tools.py` (lines 280-296)
- Impact: Progress heartbeats (long-running commands) silently fail to reach client; users see no feedback on long operations
- Fix approach: Waiting on MCP SDK fix or upstream patch; current workaround is the only solution until fixed in sdk

**Monolithic Large Files:**
- Issue: Core files exceed 1000+ lines creating single points of failure and difficult maintenance
  - `app.py`: 1441 lines (file server + MCP endpoint + multiple routers)
  - `mcp_tools.py`: 1198 lines (5 tools + progress, validation, helpers)
  - `docker_manager.py`: 756 lines (container management + networking + execution)
- Files: `computer-use-server/app.py`, `computer-use-server/mcp_tools.py`, `computer-use-server/docker_manager.py`
- Impact: Changes to one feature risk breaking others (e.g., terminal proxy changes could affect CDP proxy); harder to test specific functionality in isolation
- Fix approach: Extract specific subsystems into dedicated modules: separate terminal proxy into `terminal_proxy.py`, CDP proxy into `cdp_proxy.py`, file server into `file_server.py`; split mcp_tools into individual tool modules

**No Concurrency Control on Shared Container Resources:**
- Issue: Multiple concurrent tool calls to same container have no locking mechanism; race conditions possible on file operations
- Files: `computer-use-server/docker_manager.py` (container creation/management), `computer-use-server/mcp_tools.py` (tool execution)
- Impact: If two users share a container (single-user mode), simultaneous bash/str_replace calls could interleave, corrupting files. Idle timeout timer could kill container mid-operation.
- Fix approach: Add per-chat-id asyncio.Lock at module level; acquire before container operations. Document single-user mode limitation in system prompt.

**Dependency Version Pinning Without CVE Audit Trail:**
- Issue: While recent security patches were applied (v0.8.12.4), requirements.txt lacks comments explaining why specific versions were chosen
- Files: `requirements.txt` (40 transitive dependencies)
- Impact: Future maintainers won't know which versions are security-critical vs. optional; risk of accidental downgrades to vulnerable versions
- Fix approach: Add inline comments for CVE-patched packages (Pillow, urllib3, cryptography, PyJWT, pdfminer.six); document in security policy doc

## Known Bugs

**Single-User Mode Shared Container State Leak:**
- Symptoms: When `SINGLE_USER_MODE=""` (lenient default), all requests without `X-Chat-Id` header share 'default' container; user files/processes leak between independent conversations
- Files: `computer-use-server/mcp_tools.py` (lines 91-101, 112-128), `computer-use-server/docker_manager.py` (lines 247-250)
- Trigger: Start two separate chat sessions without setting `X-Chat-Id` header; both see shared workspace state
- Workaround: Set `SINGLE_USER_MODE=false` to reject missing headers or `SINGLE_USER_MODE=true` for genuinely single-user deployments

**Container Stale Metadata After Forced Removal:**
- Symptoms: When a container is force-removed by cron (idle timeout, disk cleanup), the metadata file (`/data/.meta/{chat_id}.json`) may remain; next tool call resurrects container with outdated MCP server config
- Files: `computer-use-server/docker_manager.py` (lines 478-484), `computer-use-server/app.py` (line 777)
- Trigger: Container runs idle for 10+ min; cron/scheduler removes it; user makes new request; container resurrects with old config
- Workaround: Manual deletion of stale `.meta.json` files; consider adding cleanup logic to container resurrection path

**Tool Loop Error Handling Patches Rely on Internal OpenWebUI Structure:**
- Symptoms: Patches `fix_tool_loop_errors.py` and `fix_large_tool_results.py` are tightly coupled to Open WebUI v0.8.11-0.8.12 middleware internals; breaking changes in v0.9+ will require rewrites
- Files: `openwebui/patches/fix_tool_loop_errors.py` (Mod 1-5 hardcoded search strings), `openwebui/patches/fix_large_tool_results.py` (Mod 2-3 path assumptions)
- Trigger: Open WebUI version bump (e.g., v0.9.0) changes middleware structure
- Workaround: Version compatibility matrix in docs; test patches after each Open WebUI release before deploying to prod

## Security Considerations

**MCP API Key Optional in Development:**
- Risk: If `MCP_API_KEY` env var is not set, `/mcp` endpoints accept all requests (no Bearer token validation)
- Files: `computer-use-server/app.py` (lines 43-68)
- Current mitigation: Docker compose runs behind proxy (nginx/LiteLLM) with rate limiting; proxy handles auth
- Recommendations: Add warning in server logs when `MCP_API_KEY` is missing; document that development deployments must be behind proxy; consider making MCP_API_KEY required in production mode

**No Rate Limiting on MCP Tools:**
- Risk: User could spawn 100+ concurrent `bash_tool` calls; each creates/manages Docker container, consuming resources
- Files: `computer-use-server/mcp_tools.py` (tool definitions), `computer-use-server/docker_manager.py` (no per-user concurrency limits)
- Current mitigation: Docker resource limits (CONTAINER_MEM_LIMIT, CONTAINER_CPU_LIMIT) prevent individual containers from consuming all resources
- Recommendations: Add per-chat-id concurrency limit (e.g., max 3 concurrent tool calls); implement sliding-window rate limiter; log abuse attempts

**Bare `shlex.quote()` Doesn't Protect Against Shell Injection in Edge Cases:**
- Risk: While `shlex.quote()` handles most cases, if command construction uses string interpolation before quoting, injection is possible
- Files: `computer-use-server/mcp_tools.py` (lines 614, 650, 841, 854, 857, 859, 898-906), `computer-use-server/docker_manager.py` (lines 393, 557, 608)
- Current mitigation: Input validation via `sanitize_chat_id()`, header validation, path normalization via `safe_path()`
- Recommendations: Audit command construction paths for unquoted interpolation; prefer structured command arrays where possible (e.g., `subprocess.run(['bash', '-c', command])` vs. string building)

**Container File Permissions Overly Broad:**
- Risk: Directory creation in `docker_manager.py` line 393 uses `chmod -R 777` on user data paths, allowing container escape + host compromise if container is compromised
- Files: `computer-use-server/docker_manager.py` (line 393)
- Current mitigation: Container runs as unprivileged user (`assistant:assistant`); no privilege escalation in Dockerfile
- Recommendations: Use more restrictive permissions (755 for dirs, 644 for files); document privilege model; add SELinux/AppArmor profile if available

## Performance Bottlenecks

**Synchronous Docker Operations Block Event Loop:**
- Problem: `_get_or_create_container()`, `_execute_bash()` are synchronous; called via `asyncio.to_thread()`, blocking thread pool
- Files: `computer-use-server/mcp_tools.py` (lines 398-401, 424-426, 543, 609), `computer-use-server/docker_manager.py` (entire module)
- Cause: Docker SDK doesn't have async support; each tool call waits for sequential container creation/command execution
- Impact: Under high concurrency (10+ simultaneous requests), thread pool saturation causes queueing delays; tools appear slow
- Improvement path: Migrate to async Docker client (e.g., `aiodocker`) or implement container pooling to reduce creation overhead

**Progress Heartbeat Hardcoded to 15-Second Intervals:**
- Problem: Long-running commands (60+ sec) send progress updates every 15s; client receives bursts of notifications
- Files: `computer-use-server/mcp_tools.py` (lines 414)
- Impact: For 10-minute commands, 40+ progress messages generated; not critical but inefficient
- Improvement path: Adaptive heartbeat based on command duration; exponential backoff for very long operations

**File Uploads/Downloads Not Streaming:**
- Problem: File upload handler reads entire file into memory; large files (100MB+) cause memory spikes
- Files: `computer-use-server/app.py` (file upload endpoint)
- Impact: Container memory limits (2GB default) get exhausted if users upload large media files
- Improvement path: Implement streaming upload/download with chunked processing; validate file size before upload

**Skill Manager Loads All Skills on Every Request:**
- Problem: `skill_manager.get_user_skills_sync()` reads from disk/API on each container creation; no caching
- Files: `computer-use-server/docker_manager.py` (line 432-434), `computer-use-server/skill_manager.py`
- Impact: With 50+ user skills, each tool call incurs 50+ file reads; visible latency
- Improvement path: Cache skill list per session (TTL 5 min); invalidate on skill upload; add metrics

## Fragile Areas

**Terminal Proxy WebSocket Forwarding:**
- Files: `computer-use-server/app.py` (lines 680-722)
- Why fragile: Multiple nested try/except blocks with bare `pass`; connection drops (client disconnect, backend timeout) silently fail to notify peer; task cancellation leads to orphaned connections
- Safe modification: Replace bare except handlers with explicit close() + logging; add health check endpoint; implement connection pooling
- Test coverage: No unit tests for WebSocket forwarding; only integration tests in shell scripts

**Single-User Mode Default Behavior:**
- Files: `computer-use-server/mcp_tools.py` (lines 91-101), `computer-use-server/docker_manager.py` (lines 247-250)
- Why fragile: Lenient default (`SINGLE_USER_MODE=""`) auto-creates 'default' container for any request; intended for single-user Claude Desktop, but untrained users deploying to multi-tenant environments unknowingly expose shared state
- Safe modification: Change default to strict (`SINGLE_USER_MODE=false`); require explicit opt-in for lenient mode; improve logging with prominent warnings
- Test coverage: 13 unit tests in `tests/orchestrator/test_single_user_mode.py`; good coverage but scenario of accidental multi-tenant leak not explicitly tested

**Open WebUI Patch Version Compatibility:**
- Files: `openwebui/patches/*.py` (9 patches)
- Why fragile: Each patch targets specific Open WebUI versions (v0.8.11-0.8.12); no version detection or graceful degradation; patch fails silently if target marker not found
- Safe modification: Add version detection in patches; log warnings if patch can't apply; implement fallback behavior or skip gracefully
- Test coverage: Patches tested in docker build (Dockerfile RUN apply patches); but no unit tests for patch logic itself

**MCP Server Initialization Handles Missing Headers Gracefully:**
- Files: `computer-use-server/mcp_tools.py` (lines 1075-1099)
- Why fragile: Context variables default to empty strings if headers missing; downstream code assumes non-None values; can cause silent failures in GitLab token fetch or MCP server config
- Safe modification: Explicit null checks before using context values; early validation at tool boundary; document required vs. optional headers clearly
- Test coverage: No tests for missing header scenarios; `test_mcp_tools.py` doesn't cover header validation edge cases

## Scaling Limits

**Container Per-Chat Approach Doesn't Scale to Thousands of Concurrent Users:**
- Current capacity: ~50-100 concurrent containers on typical host (2GB memory limit × 2GB allocations = 4-8 containers practical max)
- Limit: Database bottleneck when loading/saving metadata for 1000+ chats; Docker daemon overhead
- Scaling path: (1) Implement container pooling + reuse across chats (sandbox isolation challenge), (2) Multi-host orchestration (Kubernetes), (3) Serverless container model (AWS Lambda)
- Timeline: Not blocking for v0.8.x; revisit if usage exceeds 100 concurrent users

**Idle Container Cleanup Requires Manual Cron Job:**
- Current capacity: Storage grows unbounded; each terminated container leaves metadata + workspace directories
- Limit: After 1000+ terminated sessions, `/data` directory exhausted; metadata file lookups slow down
- Scaling path: Implement automatic cleanup in orchestrator (check every 10 min, remove >1h idle containers); archive old metadata to cold storage
- Timeline: Medium priority (can be addressed in v0.9 with background task scheduler)

**File Archive Download Not Paginated:**
- Current capacity: Creating ZIP of all files (uploads + outputs) for large users (100+ sessions × 100MB each = 10GB+) consumes all memory
- Limit: Archive downloads fail for users with >1GB total data
- Scaling path: Implement paginated archive downloads (monthly archives); stream to disk before returning; add size warning + confirmation
- Timeline: Low priority; typical users <100MB total

## Dependencies at Risk

**OpenAI SDK Version Constraint Loose:**
- Risk: `openai>=2.20.0` allows auto-upgrade to breaking changes; sub_agent tool uses OpenAI SDK indirectly
- Files: `requirements.txt` (line 44)
- Impact: If OpenAI releases 3.0.0 with API changes, sub_agent breaks without warning
- Migration plan: Pin to `openai>=2.20.0,<3.0.0` until OpenAI 3.x compatibility tested

**Pillow 12 API Migration Incomplete:**
- Risk: LANCZOS resampling API changed from `Image.LANCZOS` to `Image.Resampling.LANCZOS` in v12; code migrated but edge cases may exist
- Files: `computer-use-server/mcp_tools.py` (image resizing), skills using Pillow
- Impact: If skills use old API, they'll fail silently with warning logs but no clear error message
- Migration plan: Grep for `Image.LANCZOS` without prefix; update all occurrences; add test covering old + new API

**pdfminer.six RCE Fix Assumed Incompatible:**
- Risk: v20251230 includes pickle deserialization RCE fix; but no changelog documenting breaking changes
- Files: `requirements.txt` (line 16)
- Impact: If code relies on pickle deserialization features, it breaks without clear error
- Migration plan: Review pdfminer.six usage in PDF extraction skills; test with v20251230 explicitly; document breaking changes

## Missing Critical Features

**No Monitoring/Alerting on Tool Failures:**
- Problem: Tool errors logged to stdout only; no centralized error tracking, no alerts for sustained failures
- Blocks: Production deployment without observability; can't diagnose widespread issues affecting users
- Priority: High — needed before scale to 10+ concurrent users
- Implementation: Add OpenTelemetry/Datadog instrumentation; capture tool call counts, error rates, latencies

**No Audit Trail of Tool Calls and Results:**
- Problem: No persistent record of what commands were executed, results returned; can't replay/recover from accidental deletions
- Blocks: Enterprise deployments requiring audit compliance; troubleshooting user issues
- Priority: Medium — nice-to-have for v0.9
- Implementation: Log tool calls (sanitized) to structured event store; query interface for chat history retrieval

**No Graceful Shutdown Sequence:**
- Problem: No signal handler for SIGTERM; orchestrator dies abruptly, leaves containers running, connections orphaned
- Blocks: Clean container cleanup on redeploy; coordinated multi-replica deployments
- Priority: Medium — impacts deployment reliability
- Implementation: Add SIGTERM handler; flush pending operations; stop accepting new requests; wait for in-flight tools (30s timeout); shutdown containers

## Test Coverage Gaps

**WebSocket Forwarding (CDP/Terminal Proxy) Not Tested:**
- What's not tested: Connection drops, timeout handling, data loss scenarios, concurrent connections
- Files: `computer-use-server/app.py` (lines 640-722)
- Risk: Silent connection failures; terminal appears frozen; user loses work mid-session
- Priority: High
- Recommended tests: (1) Backend disconnect mid-stream, (2) Client timeout + reconnect, (3) Concurrent connections to same container, (4) Large data frames (10MB+)

**MCP Tools with Non-Default Headers Not Covered:**
- What's not tested: Custom GitLab tokens, MCP servers injection, anthropic API key override
- Files: `computer-use-server/mcp_tools.py` (lines 1075-1099)
- Risk: Custom auth flows fail silently; users can't use private repos or custom models
- Priority: Medium
- Recommended tests: (1) X-Gitlab-Token header injection, (2) X-Anthropic-Api-Key override, (3) X-Mcp-Servers custom server config, (4) MCP Tokens Wrapper fallback

**Error Recovery Paths in Tool Loop:**
- What's not tested: Container removal mid-command, Docker daemon restart, network partitions
- Files: `computer-use-server/mcp_tools.py` (lines 376-437), `openwebui/patches/fix_tool_loop_errors.py`
- Risk: Transient failures treated as permanent; users see cryptic errors instead of retry suggestions
- Priority: Medium
- Recommended tests: (1) Simulate container killed during bash_tool, (2) Docker daemon unavailable, (3) Network timeout + recovery

**Skill Manager Loading Failure Scenarios:**
- What's not tested: Skill registry down, malformed SKILL.md, missing skill entrypoints
- Files: `computer-use-server/skill_manager.py`
- Risk: Failed skill loads crash container creation; user can't start new chat; cascading failures
- Priority: Medium
- Recommended tests: (1) HTTP 500 from skill registry, (2) Invalid SKILL.md YAML, (3) Missing skill entrypoint file

---

*Concerns audit: 2026-04-12*
