<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

# D5 per-chat storage isolation - corrected build spec (ADR-0030)

NOT committed. Working spec. The design workflow (wf_74cc3736-ac1) produced a full
per-repo spec; an adversarial critique ruled the FIRST draft UNSOUND on two blockers.
This is the corrected (SOUND-WITH-FIXES) spec the builders implement. Delete when D5 lands.

## The two blockers the critique caught (both fake-green traps) - CORRECTED HERE

**B1 (Finding 2): the status-verb resolve path could not read `effective_scope`.**
`Manager.Status` -> `LookupForCaller` -> `store.LookupSession` returns the FROZEN
`state.SessionRow`; `effective_scope` was proposed on `EnrichedSessionRow` (a
different type the frozen lookup never returns). Every chat would silently resolve
the base -> defect un-fixed behind green shim-keystones.
CORRECTION: add `LookupForCallerEnriched(ctx, key, owner) (state.EnrichedSessionRow, error)`
on the Custodian that type-asserts the optional `EnrichedLister` seam (mirror
`EnrichedLiveSessions` registry.go:306), and route the status verb through a new
`Manager.StatusEnriched` that returns the enriched row. `effective_scope` lives on
the enriched row ONLY (no widening of the frozen Phase-1 core). Keystone must drive
THIS read path (not a stubbed recorder).

**B2 (Finding 1): the north "namespace authz" compared two client-supplied headers.**
`X-OCU-Filesystem-Id` (X) and the proposed `X-OCU-Filesystem-Base` (B) are BOTH set
by the same client. Base-containment `X == B OR X == B+"-"+16hex` is satisfiable by
any caller for any target -> a shape-linter, not authorization. It enforces NOTHING
against the peer-chat threat.
CORRECTION: DROP the pretense. `namespaceScopeSource` is a SHAPE + TRAVERSAL guard
only (rejects `/`, `\`, NUL, and a scope not matching `base OR base-16hex`), and D5
per-chat isolation at the north face is CLIENT-COOPERATIVE, matching ADR-0030's own
deferred within-tenant boundary (#348). Remove all "cross-base IS enforced" language.
The REAL isolation that D5 delivers is on the SOUTH/mint path: control derives a
distinct scope per (attested owner, handle), mints it into the JWT claim, and the
edge/engine key on the validated claim - a peer chat's guest gets a DIFFERENT
credential and physically cannot read another chat's objects. That is the load-bearing
property. The north face is the file-pane's cooperative view, hardened only for shape.

## What D5 ACTUALLY delivers (the honest scope, owner already ruled "full D5")

- SOUTH isolation is REAL and cryptographic: two chats -> two derived scopes -> two
  JWT claims -> two credentials -> guest B cannot read guest A's outputs. This is the
  cross-chat file-visibility path the ADR names. PROVABLE and the acceptance keystone.
- NORTH (file pane) isolation is CLIENT-COOPERATIVE for v1 (#348 deferred), because
  the embed token attests a tenant, not a chat, and hardening it to per-chat needs the
  chat id on an attested channel (embed-token claim) - explicitly the #348 open question.
- Backward compat: `-derive-chat-scope=false` (default) = today's single static scope.

## Per-repo (corrected)

### control @fix/146-plural-mount-intents  [Wave 1, critical path]
- NEW internal/lifecycle/scopehandle.go: `scopeHandle(owner state.Identity, handle string) string`
  = lowercase-hex SHA-256 over length-prefixed (`writeField`) pre-image
  [version "ocu-scope-v1", owner.Tenant, owner.Caller, handle], truncated to 16 hex.
  SPDX FSL header. Deterministic; no salt (version = domain sep).
- stages.go: NEW `stageDeriveChatScope` inserted IMMEDIATELY BEFORE the
  `mintStorageJWT` entry in `m.stages` (critique Finding 4: not "between S4 and S6" -
  the slice has quotaCharge/reserve/handoff between; pin it right before mint, after
  handoff sets st.handle/st.owner). Gated on `m.deriveChatScope`; no-op + `(nil,nil)`
  otherwise. Rewrites each mount `FilesystemID = base + "-" + suffix` in place;
  fail-closed `ErrScopeTooLong` if result > 256. Sets `st.effectiveScope`.
  Confirm noorphan_test.go regenerates fault points from len(m.stages) (comment says
  it does) so the no-op stage is auto-covered; document it is intentionally
  compensator-free.
- manager.go: `deriveChatScope bool` config field; `createState.effectiveScope string`;
  after commit, non-fatal `RecordEffectiveScope(ctx, key, effectiveScope)` (recovery =
  re-derive from persisted owner+handle).
- registry.go: `EffectiveScopeRecorder` capability (mirror ActivationRecorder) +
  `Custodian.RecordEffectiveScope` + **`Custodian.LookupForCallerEnriched`** (B1 fix,
  type-asserts the EnrichedLister seam, ErrNotOwned on foreign/absent - same audience
  scoping).
- state: `EnrichedSessionRow.EffectiveScope *string` (nullable); postgres schema
  `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS effective_scope TEXT` (durable column,
  NOT the LastActivity overlay); postgres.go SELECT + scan + `RecordEffectiveScope`
  (durable UPDATE); inmem.go mirror; statetest conformance arm `TestEffectiveScopeRoundTrips`
  (record+read-back both legs; never-recorded reads nil).
- ingress/operator/read.go: `SessionView.EffectiveScope *string`.
- ingress/gateway/serve.go: `sessionResponse.EffectiveScope string` json omitempty;
  route the status verb through **`Manager.StatusEnriched`** (B1 fix) reading the
  enriched row for the caller's OWN key.
- cmd/ocu-controld/config.go: `-derive-chat-scope` bool default false; also reject a
  base matching `.*-[0-9a-f]{16}$` at boot when derivation on (critique Finding 7).
- KEYSTONES:
  - `TestTwoChatsMintDistinctDerivedScopes` (NON-VACUOUS): deriveChatScope=true, two
    hints chat-a/chat-b, read minted claim + wire mount fsid; assert claim(a)!=claim(b),
    both prefix "fs-1-", suffix ^[0-9a-f]{16}$, wire fsid==claim. Red-probe: no stage ->
    both "fs-1" -> assertion (1) REDs.
  - `TestDeriveDisabledKeepsBaseScope`: flag off -> both bare "fs-1" (degrade green).
  - `TestEffectiveScopePersistedAndOnStatusEnriched` (B1-aware): after create,
    StatusEnriched for same caller returns effective_scope "fs-1-<hex>"; DIFFERENT
    caller -> ErrNotOwned. Red-probe: route Status through the NON-enriched lookup ->
    empty scope -> RED (proves the enriched read path, not a stubbed recorder).

### filestore @fix/d6-sha256-manifest  [Wave 1]
- internal/filesapi/scopesource.go: `namespaceScopeSource` = SHAPE/TRAVERSAL guard only
  (B2 correction). Reject scope containing `/ \ NUL` or not matching `base OR
  base-[0-9a-f]{16}` (the 16-hex shape pins the derivation alphabet + rejects fs-fleetX
  as MALFORMED, not as "cross-base authz"). No base header authz claim. Absent base ->
  degrade to headerScopeSource behavior. Doc-comment: this is cooperative shape hardening,
  NOT per-chat authz (#348). Keep 503 deny (no scope-distinction leak).
- main.go: wire NewNamespaceScopeSource().
- KEYSTONE `TestNamespaceScopeShapeGuard`: fs-fleet-<16hex> 200; fs-fleetX 503 (shape,
  non-vacuous vs raw HasPrefix); fs-fleet-abc/123 denied (traversal); no-base fs-fleet
  200 (degrade). Framed as shape-guard, not authz.

### webui @main  [Wave 2]
- Cooperative per-chat scope via embed-token claim (Option A). f9.ts emits
  X-OCU-Filesystem-Id = session.filesystem_id (may be derived). Cookie NAME chat-scoped
  (cookie.ts) so concurrent panes keep distinct sessions (critique Finding 6: REQUIRED,
  not deferred, because J6 needs distinct jars).
- KEYSTONE cross-tenant.test.ts `TestChatScopeIsolationSameBase`: two sessions distinct
  derived fsids over one store -> A lists none of B; own-chat green; cross 404. Framed as
  cooperative (the real enforcement is south).

### fleet/open-computer-use @docs/demo-walkthrough  [Wave 3]
- control compose: `-derive-chat-scope=true`; assert filestore `-claims-bind=true` in J6
  preflight (critique Finding 8: the derived claim must actually land or J6 is vacuous).
- embed-portal: resolve effective_scope via control status verb (portal holds gateway
  cred), mint into embed token.
- openwebui tool: `_resolve_chat_scope(chat_id)` via gateway status verb (bearer +
  X-Chat-Id), NEVER local hash; thread scope into _sync_uploaded_files; degrade to base.
- SOUTH first-write provisioning (critique Finding 5) - FABLE RULED Option A: a
  filestore DAEMON-LAYER lazy-scaffold decorator (engine interface + impls UNCHANGED).
  Files (ocu-filestore): (1) cmd/ocu-filestored/main.go - hoist the boot-scaffold block
  (~1425-1461: eng.ProvisionScope + the SubtreeMap MakeDir loop) into a
  scaffoldScope(ctx, eng, scope, subtrees) helper; (2) NEW internal/objectstore/
  engine_lazyprovision.go - a decorator wrapping Engine that, on the first data verb per
  UNSEEN scope whose name passes the wave-1 derived-shape predicate (<bootBase>-<hex16>),
  calls scaffoldScope then delegates; non-derived non-base names refuse exactly as today
  (fail-closed preserved). Apply the decorator ONCE at compose so north filesapi AND south
  southface both get it (kills the uploads-first/writes-first asymmetry). C was refuted
  firsthand (control has NO filestore client, filestore exposes NO provisioning endpoint,
  a mint-time call couples exec-create to storage liveness - ADR-0017 forbids). ADR-0030
  amended: engine untouched, daemon lazily scaffolds shape-validated derived scopes.
  KEYSTONE: fresh derived scope never seen by filestore; FIRST op = south write-intent to
  outputs/f.txt -> succeeds, object listable under <derived>/outputs/. Red-probe 1: remove
  decorator -> first write refuses. Red-probe 2: validated cred bearing malformed scope
  (wrong hex length) -> still refused, no dir created (fail-closed intact).
- ACCEPTANCE KEYSTONE J6 `test_j6_cross_chat_file_isolation` (the ONE load-bearing gate):
  on the GATEWAY wire (X-Chat-Id, not FleetBackend). chat A writes /mnt/user-data/outputs/
  secret-a.txt; assert A and B resolve DIFFERENT effective_scope via the status verb
  (proves the resolve path - critique Finding 3); chat B guest ls + pane list -> secret-a.txt
  ABSENT; B pane read of A file id -> 404. Red-probe: flag off -> shared fs-fleet -> B sees
  A -> RED; AND stub status verb to echo base -> RED.
- DEGRADE J7: flag off -> J1-J5 two-way flow stays green.

## Build order
Wave 1: control (critical path) || filestore (independent). Wave 2: webui (needs status
verb + cookie-name). Wave 3: fleet journeys J6/J7 (needs whole chain live on Lima).
South-provisioning ruling BLOCKS J6 agent-writes-first - resolve first.

## Discipline
canon-change-first: ADR-0030 must be EDITED to match the honest scope (north = cooperative
shape guard, south = real isolation) BEFORE code - the current ADR text over-claims north
enforcement (critique Finding 1). Owner-gated to push/merge. TDD red-probe non-vacuous.
Scrub ^+ forbidden+non-ASCII. SPDX FSL on new files. Trailers Co-Authored-By: Claude Fable 5
+ Claude-Session. Consult Fable not owner.
