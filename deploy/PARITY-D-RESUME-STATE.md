<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# D1-D8 parity: resume state (session-limit checkpoint 2026-07-11)

NOT committed. Working scratch so a fresh context resumes the live-verification
cleanly. Delete when D1-D8 land.

## Where the code is (all LOCAL, owner-gated to push/PR)

- openwebui: branch `docs/demo-walkthrough` @64d2e06 (D1/D2/D3 system_prompt.txt +
  init.sh + Dockerfile; D6/D4-client + D7 in tools/computer_use_tools.py; K1/K2
  tests in deploy/tests/). Committed, scrub-clean.
- gateway: branch `fix/parity-d8-d4` @4c07403 (D8 command_semantics + D4 view
  image/binary). Also merged into `combo/146-parity` @94f1b89 (= plural-mount
  146 base + D8 + D4) for the stand. Committed, `go test ./...` green.
- filestore: branch `fix/d6-sha256-manifest` @e5b1630 (D6 sha256 in F9 list),
  rebased onto post-#146 main @fed5b146. Committed.
- ADR-0030 (D5 canon): `feat/adr-0030-per-chat-scope` @4a834bd on next/v1
  worktree /tmp/wt-canon-next. Authored, owner-gated.

## Live-verify status (Lima ocu-linux stand, fleet-stage on branch sync/parity)

Rebuilt + recreated on the stand: gateway (combo/146-parity), filestore, openwebui,
control (plural-mount 858ec00), rclone south leg (fca37bb). Stand trees on
`sync/parity` branch. Do NOT rebuild from host - stand builds from ~/fleet-stage/*.

PROVEN GREEN (firsthand, live - ALL Wave-1/2 code defects done):
- D1/D2/D3: model params.system in openwebui-db carries <available_skills> x2,
  <sharing_files> x1, /mnt/skills/public x24, /mnt/user-data/outputs x8; ABSENT:
  "drop out of your", "sub_agent", "{file_base_url}". (re-seed via: delete
  /app/backend/data/.computer-use-initialized in open-webui container + restart.)
- D7: tool record ai_computer_use in db has_subagent=false, has_bash=true.
- D8: LIVE through real gateway - `grep zzz /etc/hostname` (exit 1, empty) returns
  isError:false + "No matches found". Red-probe: neuter the semantics-table
  threshold 2->0 in http.go -> TestCommandSemanticsGrepNoMatchesIsNotError REDs
  ("got isError:true [Exit code: 1]"); restore -> green. Non-vacuous.
- D4: LIVE through real gateway in /home/assistant (persistent; NOT /tmp - each
  tools/call is a fresh exec, /tmp does not persist). view g.png -> image_url block
  "data:image/jpeg;base64,..." (len 911) + "Image: <path>"; view s.xlsx -> isError
  true + "Read SKILL first: view /mnt/skills/public/xlsx/SKILL.md". Guest has PIL
  12.2.0 + openpyxl.
- D6: LIVE against F9 north (filestore:7080, header X-OCU-Filesystem-Id: fs-fleet,
  multipart params-part FIRST then file-part). Upload 64B "A" -> list sha256 ==
  local d53eda7a...; upload SAME-SIZE 64B "B" -> list sha256 == c422e707... (DIFFERENT).
  Same size, different content -> different sha256 -> client re-uploads (the defect
  the old name+size dedup hid). Probe via a python:3.12-slim container on the
  ocu-fleet_ocu-north network (verify=False for the diagnostic; north leaf is not
  gateway-pki signed).

STAND-STATE lesson (NOT a D-fix defect, memory'd):
  A long-lived stand wedges EVERY create at 409 (audit reason=quota-rejection)
  via the leaked DimConcurrentSessions counter. Heal: wipe control-db volume
  ocu-fleet_control-db-data + recreate control -> direct create 201. See
  reference_stand_quota_leak_wedges_create.md. The full journey suite still
  wedges after ~64 leaked slots (control [concurrency-counter-leak], pre-existing);
  the D-keystones are proven directly with few sessions instead.

## Next steps on resume (in order)

1. Heal quota: wipe control-db volume again OR raise the per-key concurrency cap
   for the stand run; confirm direct create 201.
2. Re-run the journey suite serially/with teardown so quota does not wedge:
   `cd ~/fleet-stage/open-computer-use/deploy/tests && .venv/bin/python -m pytest
   journeys/ -q` (17 passed / 32 failed last run - the 32 are ALL the quota storm).
3. Finish D4 live keystone in /home/assistant (persistent): write g.png + s.xlsx,
   view each -> PNG must return an image_url data: block, xlsx must return the
   SKILL.md hint + non-image. (bearer: ~/fleet-stage/.../deploy/fleet/secrets/gateway/bearer.txt)
4. D6 live: upload a file via F9, edit to same byte-size different content,
   re-sync -> re-uploaded not skipped (sha256 dedup).
5. D5 impl (task #153): the terrain phase of workflow wf_74cc3736-ac1 COMPLETED
   (4 mappers, results cached in that run's journal); design+critique FAILED on
   the session limit. Resume that workflow:
   Workflow({scriptPath:
   "/Users/nick/.claude/projects/-Users-nick-open-computer-use/3902ad32-f744-4909-9af2-4148370573c9/workflows/scripts/d5-terrain-design-wf_74cc3736-ac1.js",
   resumeFromRunId: "wf_74cc3736-ac1"}) - the 4 terrain agents return cached,
   design+critique re-run live. Then implement D5 per ADR-0030 across the 4 repos.

## D5 progress (2026-07-11/12)
- ADR-0030 corrected for honesty + Fable provisioning ruling: 3 commits on next/v1
  worktree /tmp/wt-canon-next (feat/adr-0030-per-chat-scope @d29eedd). Owner-gated.
- Corrected build spec: deploy/D5-BUILD-SPEC.md (SOUND-WITH-FIXES; the 2 UNSOUND
  blockers B1/B2 fixed).
- Wave-1 DONE + cold-verify PASS: control @10c6a52 (fix/146-plural-mount-intents:
  scopeHandle derivation + enriched status verb + durable effective_scope column),
  filestore @0a6647a (fix/d6-sha256-manifest: north shape/traversal guard).
- Wave-2 BUILT (cold-verify was running at checkpoint): filestore lazy-scaffold
  decorator @c34b285, webui cooperative chat-cookie @a1e5915 (ocu-webui main),
  openwebui tool + embed-portal resolve-via-status @dd59813 (open-computer-use
  docs/demo-walkthrough). Check verify before Wave-3 stand rebuild.
- Wave-3 DONE + D5 LIVE-VERIFIED (the acceptance keystone):
  - control derives distinct per-chat scopes: two chats resolve
    fs-fleet-e27eb953733bf3d1 vs fs-fleet-c894cbe13592dd5d via the status verb.
  - J6 GREEN live: chat A writes /mnt/user-data/outputs/<secret>; chat B (different
    X-Chat-Id -> different derived scope) ls shows EMPTY, cat -> No such file.
  - Red-probe (derive OFF): both chats share fs-fleet -> chat B B-SEES-A (reads A's
    bytes). Inversion by flag confirms non-vacuity.
  - Filestore S3 lazy-scaffold poison-cache bug found+fixed live (@7d77271:
    disk 100%-full -> MinIO 507 -> terminal error cache -> scope stuck 500 till
    restart; fix memoizes success only, honest 503/429 deny classes, backend-detail
    logging). Rebuilt filestore, re-verified.
  - filestore now @7d77271 (fix/d6-sha256-manifest). ADR-0030 4 commits on next/v1.
  ALL D1-D8 DONE + live-verified. Everything OWNER-GATED to push/PR/canon-merge.

## Discipline reminders
Lima native arm64, no --platform. Fresh session/recreate control to clear cached
creds. TDD red-probe non-vacuous. Scrub ^+ for forbidden literals + non-ASCII.
Push/PR + canon merge = OWNER-GATED. Trailers: Co-Authored-By: Claude Fable 5,
Claude-Session. Consult Fable not owner.
