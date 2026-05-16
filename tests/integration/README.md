# Integration tests

End-to-end tests against a real `computer-use-server` container that spawns real workspace containers via the host Docker socket. Mirrors the prod Compose/Helm setup 1-to-1 — no mocks at the HTTP boundary, no mocks at the Docker boundary.

## What's covered

| Concern | Test file | Why it matters |
|---|---|---|
| `MCP_API_KEY` auth (valid / missing / wrong) | `test_mcp_auth.py` | Refactoring out the `verify_mcp_auth` dependency would silently make `/mcp` public. Unit tests can't catch this — the dependency is wired at app construction. |
| `tools/list` matches expected name set | `test_mcp_tools.py` | A typo (`bash_tool` → `bash_too1`) ships green today; this pins the surface. |
| `tools/call bash_tool` end-to-end echo | `test_mcp_tools.py` | Catches workspace image misconfig, Docker socket missing, response wrapping regressions, sub-agent dispatch breakage. |
| `/health` is unauthenticated and returns `healthy` | `test_mcp_tools.py` | k8s probes break if either changes. |
| Workspace container has the prod labels (managed-by, chat-id, tool) | `test_workspace_lifecycle.py` | Drift in any of these labels breaks the cleanup cron's filter in prod. |
| `/mnt/user-data/{uploads,outputs}` bind mounts | `test_workspace_lifecycle.py` | Compose USER_DATA_BASE_PATH must round-trip into the spawned container. |

## How to run

### From a clean checkout (test harness owns the stack)

```bash
# One-shot: build images, bring stack up, run tests, tear down.
pytest tests/integration/ -v
```

First run rebuilds the orchestrator image (~3 min) and may pull the workspace image. Subsequent runs reuse the local cache.

### Against an already-running stack (CI matrix, dev iteration)

```bash
docker compose -f docker-compose.test.yml up -d --build
export OCU_TEST_BASE_URL=http://localhost:18081
export OCU_TEST_MCP_API_KEY=test-token-do-not-use-in-prod
pytest tests/integration/ -v
# … iterate on a single test …
pytest tests/integration/test_mcp_auth.py::test_invalid_token_returns_401 -v
# tear down explicitly
docker compose -f docker-compose.test.yml down -v --remove-orphans
```

## Cleanup

Every integration test uses a `chat_id` that starts with the `itest-` prefix (see the `chat_id` fixture). The orchestrator names spawned workspace containers `owui-chat-<chat_id>`, so the session finalizer reaps orphans by container-name filter (`owui-chat-itest-*`) plus the prod label `managed-by=mcp-computer-use-orchestrator`. This deliberately avoids a production-side env knob just for cleanup — production code does not know tests exist.

Worst-case manual cleanup, scoped to integration-test containers only:

```bash
docker ps -a --filter 'name=owui-chat-itest-' \
            --filter 'label=managed-by=mcp-computer-use-orchestrator' -q \
  | xargs -r docker rm -f
```

Do **not** filter only by `managed-by=mcp-computer-use-orchestrator` — that would also remove the developer's actively-running prod workspace containers on the same machine.

## CI

`.github/workflows/build.yml` runs this suite on every push to `main` and every PR. The job builds the workspace + server images locally (no GHCR pull), brings up the compose stack, runs pytest, and always tears down regardless of result.
