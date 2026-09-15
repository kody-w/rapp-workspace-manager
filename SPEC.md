# RAPP Workspace Manager Profile

`spec_id: rapp-workspace-manager/1`

An application of `rapp/1` identity/frames. Prototype-era routing registries
remain readable for migration compatibility, but they are not current protocol
authority. The additive Frame Anything host implements the core
**RAPP Workspace/1** protocol, uniquely `rapp-workspace/1`, under sections
11–13. The registry remains routing-only, not a new protocol, identity, task
store or unified native AI storage model.

## 1. Authority and privacy

A manager MUST remain local/private, carry a mint-once canonical `rapp/1`
workspace identity with `role: manager`, `mode: solo`, one routing `world_id`,
and a `PRIVATE / NEVER PUBLISH` guard.

`registry.json` is authoritative **only for routing**. `HOME.md` and generated
editor views are disposable projections. Source projects and native stores
retain their own authority, boundaries and native identities. The manager MUST
NOT copy, index, summarize, embed or publish project/native content.

Adapters MUST be read-only, metadata-only, bounded and no-follow. They MUST NOT
read credentials, chats, prompts, summaries, memories, attachments, source
contents, terminal pane contents or browser state. No provider delete,
disconnect, close, migration, repair, checkpoint, clone or mutation API is
allowed. The manager MUST NOT recursively index home or discover native
profiles without explicit approved roots.

## 2. Registry and closed pointer union

The registry retains `schema: rapp-workspace-manager/1`, `manager_rappid`,
`world_id`, `generated_utc`, `scan_roots`, and `workspaces`.

Additive routing fields:

- `providers`: partitions keyed by `copilot`, `claude`, `hermes`, `scout`,
  `grokbot`, and no other provider.
- `forgotten`: local suppression tombstones containing only
  `pointer_id,path,filesystemIdentity`; legacy identifier-only strings remain
  readable but cannot silently lose suppression during an upgrade.
- `editor_view`: primary manager-owned `.code-workspace` filename.
- `editor_views`: bounded list of generated filenames, all regenerated on
  pointer changes so obsolete views do not retain forgotten routes.
- `organization`: version 1 manager-owned recursive organization metadata for
  selected local pointers only.

Legacy local registries load without reminting RAPP identity. Missing extension
fields receive defaults in memory; legacy pointer version 1 remains identified
as legacy until an explicit operation verifies its filesystem binding.
Unknown fields, types, versions,
providers, cross-partition identities and world/manager mismatches fail closed.

New local pointers have `pointer_version: 2`, `pointer_type: local-directory`,
a deterministic `pointer_id`, `selection: exact|discovered`, and only:
`name,path,kind,rappid,mode,world_id,tags,filesystemIdentity`. The filesystem
identity is a validated `[device, inode]` pair. `path` is absolute, `kind` is
`directory|git|rapp-workspace`. RAPP labels require canonical validation of a
bounded root `rappid.json`; symlinked or invalid identities are ignored.

New native pointers have `pointer_version: 2`, `pointer_type`, `pointer_id`,
`provider`, `profileRoot`, and `profileIdentity: [device, inode]`, followed by
exactly one provider-specific shape:

| Discriminator | Provider-specific fields |
|---|---|
| `copilot-session` | `nativeSessionId`, `metadata` (only the nine allowlisted workspace.yaml fields), `sourceStamp`, `availability: metadata|missing-metadata` |
| `claude-project` | `nativeRoot`, `nativeKey`, `indexVersion: 1|null`, `originalPath`, `pathAssociations` (distinct originalPath/projectPath pairs), `availability: indexed|missing-index` |
| `hermes-session` / `hermes-project` / `hermes-folder` | `nativeTable`, `nativeId` (native string/integer type retained), `schemaVersion: 0`, provider-native allowlisted `metadata` columns |
| `scout-workspace` | `nativeVersion: 3`, `workspaceId`, `providerId`, `rootId` |

There is deliberately **no Grokbot workspace pointer discriminator**.
Grokbot observations contain only
`provider,profileRoot,profileIdentity,observation_version,state,mapping,observation_id`, with
`observation_version: 2`,
`state: app-detected`, `mapping: workspace-mapping-unavailable`.
The observation key is manager-owned, derived from the profile root, and
supports suppression; it is not an invented native bot/workspace ID.

Version 2 pointer keys are SHA-256 over a version-tagged JSON tuple of provider,
verified device/inode identity, native discriminator and native identity.
Local pointers bind the directory inode; native pointers bind the profile inode
without replacing their native session/project/workspace IDs.
They are manager routing keys, not
RAPPIDs, a new protocol hash contract, or evidence of trust. Copilot uses the
native session UUID; Claude uses the untouched bucket key beneath the native
projects root; Hermes uses `[nativeTable, nativeId]`; Scout uses workspace ID.
The original native fields remain available. No provider's shape is flattened
into another provider's model.

Version 1 keys validate against their original path spelling without native I/O.
They are not trusted as filesystem identity. In particular, v1 Copilot metadata
must never supply a local route or reusable YAML parse cache.

### 2.1 Local recursive organization overlay

`organization` is an additive local projection policy inside
`rapp-workspace-manager/1`. It is not a new estate protocol, wire format,
identity system, source hierarchy, task store or content index. It composes
with `rapp-workspace/1.1` by leaving the manager as the first sibling editor
root, and with RAPP/1 by leaving every manager/source RAPPID, world and frame
chain unchanged.

The object has exactly:

- `version: 1`;
- `root_group: "root"`;
- `groups`: 1–512 exact `{id,name,parent}` records;
- `aliases`: 0–10,000 exact `{pointer_id,alias}` records;
- `placements`: 0–10,000 exact `{pointer_id,group_id}` records;
- `focused_views`: exact `{filename,target_type,target_id}` records associated
  with tracked `editor_views`.

The root record has ID `root`, display name `Estate` by default and
`parent: null`. It is the only null-parent group. Every other parent is a
stable group ID. Group IDs are 1–64 lowercase ASCII slug characters beginning
with a letter; names and aliases are nonempty, trimmed, control-free UTF-8
strings of at most 128 bytes. Duplicate group IDs, alias records for one
pointer, placements for one pointer, focused filenames, orphan parents,
self/cross cycles, unknown keys, unknown versions and over-bound arrays MUST
fail closed.

Aliases and placements may reference only IDs in the current selected local
`workspaces` list. Alias text need not be globally unique; commands requiring a
workspace target MUST refuse when a case-insensitive name/alias resolves to
more than one selected pointer. Focus MUST also refuse a collision between a
group ID and a local name/alias. A pointer has zero or one placement. Zero
means it appears in the synthetic `Unorganized` section; that section is not a
group or persisted pointer identity.

Loading a legacy registry with no `organization` field MUST synthesize the
default empty overlay in memory only. It MUST NOT rewrite the source registry,
remint the manager RAPPID or upgrade local pointer identity merely by loading.
Exact/recursive scans map retained overlay references by stable pointer ID (and
the verified legacy-to-current local selection replacement where applicable).
Aliases and placements for no-longer-selected pointers are pruned. Clear and
forget do the same. Re-add does not restore a pruned placement or alias.

Focused view targets are `group`, `workspace`, or manager-internal `empty`.
`empty` has `target_id: null` and preserves a previously tracked file as a
manager-only safe projection after its target disappears. Group targets must
exist; workspace targets must be selected local pointer IDs. Focused filenames
must be tracked in `editor_views` and cannot be the primary all-selected
`editor_view`.

## 3. Provider partitions, selection and failure

Each provider partition contains exactly:

- `profileRoots`: the last successfully committed profile set;
- `requestedRoots`: the explicitly requested refresh profile set;
- `profileIdentities`: saved device/inode identities for the successful roots;
- `profileHistory`: at most 64 prior/current `{path,identity}` namespaces,
  retaining v1 spellings and v2 identities solely for protection and key migration;
- `catalog`: last-good candidate pointers, not automatically selected routes;
- `selected`: owner-selected pointer identifiers;
- `forgotten`: identifier-only suppression tombstones;
- `status: never|refreshing|fresh|stale|cleared`, `error` (content-free code or
  null), `last_attempt_utc`, `last_success_utc`;
- `pending`: Copilot's manager-owned bounded metadata checkpoint or null;
- `observations`: mapping-availability observations, not invented workspaces.

A refresh MUST replace only the requested provider partition after a complete
successful scan of **all requested profiles**. Other partitions, exact local
routes, selections and suppressions MUST be preserved. A manager write lock
prevents lost updates; a busy manager fails without replacing its registry.

Incomplete scans retain the old catalog, selection and successful timestamp.
Unreadable, busy, changed, oversized, over-count, over-time or schema-invalid
native metadata discards incomplete staging, sets stale/error, and preserves
last-good routing pointers. Errors do not imply that the native data is empty.
A successful scan may remove disappeared candidates or report an explicitly
missing metadata/index file as unresolved.

Refresh is discovery, not owner acceptance. A selection may remain unresolved
when its native identity disappears; it becomes usable only when an
authoritative metadata reference and verified local directory are available.

## 4. Native read surfaces

### Copilot CLI

Enumerate only direct directories in `PROFILE/session-state`, retaining UUID
names. Read only each UUID's `workspace.yaml`. Allowlisted fields:
`id,cwd,git_root,repository,host_type,branch,client_name,created_at,updated_at`.
Present IDs MUST match the native directory UUID. The reader accepts bounded
single-line plain/quoted/null scalars in one top-level mapping, using LF or CRLF.
All keys, including ignored keys, require structural validation before proceeding
to another key. Unsupported quoted continuations, flow collections, anchors,
tags, indentation, alternate line separators and multiple documents fail
closed. Only ignored indented block scalars can span lines; those lines remain
opaque. Unknown content-bearing values are never retained as pointer metadata.

Use a bounded one-level inventory and metadata batches. A checkpoint includes
inventory directory stat fingerprints, native UUID names, offset and staged
allowlisted pointers. Incomplete staged candidates are never active routes.
Revalidate membership stamps on resume/completion. Reuse a prior metadata
version 2 pointer only when its no-follow file stat fingerprint is unchanged.
On a cache hit, return a new pointer bound to the current verified profile
locator and unchanged profile/session identity. Do not retain an obsolete
`profileRoot`, mutate the prior catalog, or leak a missing namespace `KeyError`;
namespace inconsistency is a stale metadata error.
Version 1 checkpoints restart and version 1 caches are reparsed, never promoted
unchanged. Missing
workspace metadata yields an unresolved identity, never a guessed repository.

Do not read events.jsonl, session.db, files/, checkpoints, research, rewind,
summaries, todos or search. Copilot `data.db` is **not implemented**; it would
require a separate schema-gated, WAL-aware read-only adapter.

### Claude Code

Enumerate one level beneath `PROFILE/projects`. A present
`NATIVE-KEY/sessions-index.json` MUST have integer `version: 1` and an entries
array. Keep the native root/key, top-level originalPath and all distinct
originalPath/projectPath associations. Entries may provide their own
originalPath; otherwise the top-level association applies. No transcript,
session content, memory, history, plan, instruction or attachment fallback
is permitted.

Missing index means `missing-index`, no path associations, no inferred path.
Hyphenated keys MUST NOT be decoded, even where a guessed directory exists or
punctuation yields apparent collisions.

### Scout

Read only `PROFILE/m-sessions/workspaces.json` with integer `version: 3` and
`workspaces: [{id,providerId,rootId,...}]`. Preserve those three fields plus the
native manifest version. Unknown manifest versions or structural shapes are
refused.

Only exact `providerId: local` permits rootId to be considered a filesystem
reference, and it still requires no-follow local verification. ODSP and other
providers' rootIds are opaque regardless of appearance. Protect
`PROFILE/workspace` and all provider-store directories from editor selection.
Never call Scout delete/disconnect or inspect session/browser/auth state.

### Grokbot

Check only the explicitly supplied app/runtime root directory. Recognized leaf
names are `Grokbot.app`, `.grokbot`, and `Grokbot`, case-insensitively. Existence
supports only a root-detected observation, not executable/runtime health and
not a durable bot→workspace mapping.

App support, `.grokbot`, `.grok/skills`, caches, daemon/settings and opaque
persistence MUST NOT be registered as workspaces. No persistence is read. A
real owner-selected project directory can be an independent local pointer.
A future documented export requires a separately reviewed implementation;
none is currently guessed or consumed.

## 5. Hermes read-only snapshot gate

Only `PROFILE/state.db` metadata queries are permitted. Inspect schema metadata
without retrieving table SQL/default values or application blobs. Require
`user_version = 0` and ordinary (not virtual/view) tables with a declared TEXT
or INTEGER `id`. The reviewed metadata-column allowlists are:

| Optional native table | Allowlisted columns (only present columns selected) |
|---|---|
| `sessions` | `id,parent_session_id,project_id,folder_id,cwd,created_at,updated_at` |
| `projects` | `id,path,created_at,updated_at` |
| `folders` | `id,project_id,path,created_at,updated_at` |
| `project_folders` | `id,project_id,path,created_at,updated_at` |

At least one recognized table must exist. An incompatible recognized table
fails the provider refresh. These structural gates are conditional support,
not a claim that the installed product has any particular project model.
Missing fields stay absent/unknown. Retain native table names, relationship
IDs and ID types; do not merge folder/project/session identities or derive
cwd from a project link, terminal breadcrumb, message, title or pane.

Open the database inode through descriptor-relative no-follow I/O. The trusted
OS `/dev/fd` alias pins that inode for SQLite, not an untrusted native symlink.
Use an immutable read-only URI, zero busy timeout, connection-only query-only/
memory-temp/untrusted-schema restrictions, a SQL column authorizer and a
cooperative progress handler. SELECT only allowlisted columns, with bounded
scalar transfer and row counts.

Before/after queries, check no-follow main-file and sidecar metadata. Do not
open a native WAL or SHM for content. A nonempty WAL or journal, busy SQLite
lock, file replacement/change, schema mismatch or unavailable safe interface
MUST fail closed with last-good retention. The shared SQLite lock-byte read
lock is held only during the bounded query. Never ignore active WAL, create
SHM, checkpoint, repair, or copy the database. Active-WAL ingestion is not
supported.

## 6. Exact roots, clear and suppression

`estate` / `scan --mode exact` select exactly the supplied local roots, including
non-Git directories, without recursion. The manager is never a project
container. Ancestor/descendant overlap between a routed directory and the
manager, or between selected local roots and a native store, is refused.
Native catalogs are not silently registered through local scanning.

Recursive scanning continues to discover nested repositories and worktree
markers, excluding symlinks, pruned build/native directories and the manager
subtree. It replaces only Git-discovered local entries, retaining exact local
selections and provider state.

`clear` / `clear-cache` remove only manager-owned pointers/caches, selections
and projections. A later explicit scan/refresh may rediscover an unselected
native candidate. `forget` additionally persists a suppression tombstone
until explicit `re-add`. Clear-cache MUST NOT remove tombstones. Forgetting a
whole known catalog does not suppress future unknown native identities.
Re-add does not fabricate native data: a suppressed native ID remains pending
rediscovery before it can resolve locally.

Local tombstones retain both original location and device/inode identity,
covering case/slash aliases, renames and replacement at the original location.
Re-add explicitly removes matching suppression. An old identifier-only local
tombstone cannot prove the former filesystem identity; new local scanning fails
closed until explicit original-spelling re-add or owner repair of manager
metadata. No automatic upgrade may discard an unknown tombstone.

Native namespace history allows a complete successful scan to translate v1
keys and known profile aliases while preserving suppression. Native session,
bucket, table and workspace identities must still match exactly; no new native
identity is inferred. Incomplete/error scans never apply a partial key migration.
Conflicting saved device/inode identities MUST NOT be treated as aliases by
pathname equivalence. Their original tombstones and selections remain bound
to the original objects; replacement objects do not inherit acceptance.
Ambiguous legacy path-hash suppression fails closed with
`native-identity-ambiguous` until explicit re-add/identity selection. It MUST
NOT be transferred to another inode or consumed while guessing a migration.

Migration MUST be two-phase. First snapshot the original selection/suppression
sets and plan every candidate and observation without mutating those sets.
Evaluate all ambiguity against the original suppression set, and refuse if
multiple distinct targets claim one original selected/suppressed identity.
Only after the complete plan is validated may removals and additions be
applied as set operations; suppression wins over selection. Candidate/profile
order MUST NOT affect acceptance, refusal or the resulting routing sets.

Clear/forget discard in-progress provider staging, preserve other partitions,
and regenerate all tracked manager views. No source identity or history is
rewritten. A duplicate local name MUST fail closed during open/resolve.

Grokbot observation IDs support clear/forget/re-add with the same durable
tombstones, but can never enter `selected` or become editor roots. Re-add of
an observation only enables later rediscovery; it never invents a mapping.

## 7. Safe deterministic projections

The all-selected editor view contains the manager first, then selected local
entries in owner order, then explicitly selected native references in
deterministic provider/identifier/path order. Dedupe filesystem objects by
device/inode for the view only; never collapse distinct native identities. A
Claude selection can contribute multiple verified local associations. Copilot
uses explicit cwd, otherwise explicit git_root; Hermes sessions without cwd
stay unknown.

A focused group view contains only selected local pointers placed directly in
that group or recursively in descendant groups. A focused workspace view
contains only its one selected local pointer. Both retain the manager as first
folder and omit native-provider selections. The default filename is derived
deterministically from the stable group or local pointer ID and remains a
direct manager child. `--print-path` resolves and prints only workspace
targets; group targets MUST be refused.

Only existing absolute no-follow local directories are folders. Unknown,
missing, protected and nonlocal references remain visible in the dashboard/
catalog. Native roots are never converted to filesystem paths by guessing.

Normalize ambiguous leading slash forms to the ordinary local root. Use
no-follow descriptor identity and bounded kernel parent traversal to compare
home, manager and registered native ancestry. Lexical prefixes, global
case-folding or symlink-following realpath MUST NOT decide object identity or
authorization. Filesystem lookups determine each volume's case behavior.
Local routes must still match their stored filesystem identity when projected
or opened; replacement at the same path requires explicit re-add.

Current protection locators are checked with no-follow I/O. A historical
locator contributes resolved ancestry only if it still matches its saved
identity; its remembered object identity remains protected independently.
Missing, inaccessible, symlinked or reused obsolete historical locators are
isolated, not followed or allowed to invalidate unrelated healthy routes.
Verified current locators retain native-object and ancestor protection during
editor generation, opening, exact selection and recursive discovery.

Editor output filenames MUST be direct children of the private manager and
end in `.code-workspace`. Preserve unrelated JSON/JSONC settings, extensions
and top-level values; replace only `folders`. Comments/formatting need not
survive. Unicode-normalized, case-folded filename aliases are conservatively
treated as one output so projections cannot overwrite one another on
case-insensitive filesystems. Corrupt/unsafe outputs fail closed. The dashboard renders escaped
metadata only and caps its native preview at 100 candidates per provider.

Writes use exclusive same-directory staging, flush/fsync, atomic replace and
directory fsync; manager output symlinks and multi-link files are refused.
Metadata readers and manager locks also refuse hardlinks before reading content
or locking; lock descriptors are read-only. `HOME.md` includes at most 200
organization-tree lines and never reads routed content. Registry and projections
are each atomic, **not a multi-file transaction**. Registry is committed first;
after a crash regenerate projections from it. Retained editor filenames ensure
that previously generated all-selected and focused views can also be rebuilt
after routing or organization changes.

## 8. Bounds

Default/hard scan limits: entries 150,000/200,000; Copilot metadata batch
1,000/10,000; individual metadata file 2/8 MiB; per-invocation metadata bytes
16/64 MiB; cooperative deadline 10/60 seconds. Count ignored entries too.

Fixed limits: 16 provider roots, 64 namespace-history entries per provider,
128 recursive scan roots, 10,000 explicit exact roots, recursive depth 64,
128 lexical path components and kernel ancestry steps, 4 KiB strings, 32 root
routing tags, 64 KiB root RAPP identity file, 128 MiB compact provider
catalog/stage, 512 MiB manager registry, 16 editor views, 8 MiB existing editor
file, 2 GiB Hermes database stat size, 512 organization groups, 10,000
organization aliases and 10,000 organization placements. Editor folder
resolution allows 10,000 folders and a 10-second cooperative verification
deadline. Checks include regular-file types, no-follow ancestors/leaves,
before/after file stamps and bounded transfer. Unsupported no-follow platforms
fail closed.

Deadlines cannot preempt one stalled OS syscall. Copilot inventories are
bounded O(N) directory-name snapshots; metadata reads are incremental, but
serializing/validating the manager checkpoint/catalog is also O(N).
Multi-batch observations are not native transactional snapshots.

## 9. Python API and commands

- `native_ai.scan_provider(provider, profile_roots, previous=(), pending=None,
  limits=None)` performs read-only inspection, returning `complete`, `catalog`,
  `observations`, `pending`, `examined`, `reused`, provider/profile metadata.
  Errors are content-free `RoutingError` codes.
- `workspace_manager.refresh_provider(workspace, provider, profile_roots=None,
  limits=None)` performs a locked, provider-scoped manager-only merge.
- `workspace_manager.provider_action(workspace, provider, action,
  pointer_id=None)` supports `select`, `clear`, `clear-cache`, `forget`,
  `re-add` and no native lifecycle operations.
- CLI: `provider inspect|refresh|list|select|clear|clear-cache|forget|re-add`,
  `estate`, `scan --mode recursive|exact`, `editor-view`,
  `group add|remove|assign|unassign`, `tree`, `focus`, and local
  `list|open|clear|clear-cache|forget|re-add`.

`group remove` refuses the logical root and groups with child groups or direct
placements. `tree` renders the recursive group structure followed by
`Unorganized`. `focus --target` accepts a group ID or a unique case-insensitive
selected local name/alias. `open --name` accepts the same local name/alias
resolution and prefers `code -n` before the existing safe platform fallback.

Inspect/list never write native data or manager state. Refresh exits 1 on
stale/error and 0 for complete or bounded in-progress work. Selection and
suppression mutate only manager state and projections.

## 10. Frame authority and public/private split

Generated managers retain the canonical `rapp-projects/tools/append_frame.py`
writer. Manager project history MAY use existing `body.pulse` frames carrying
`work.status` when repository convention requires it. Never mint an estate
protocol/event merely to represent a pointer view. Existing source frames and
branches stay immutable and source-owned; no copied backlog is permitted.

Every emitted frame MUST use the canonical RAPP/1 implementation, validation,
prior payload hash link and atomic write. Verification evidence MUST include
at least one existing/emitted frame, not a zero-artifact pass. Structural
verification does not supply authenticated acceptance or owner authority.

The development `tools/check_conformance.py` runs the unchanged canonical
checker plus the existing writer's canonical chain verifier and requires a
nonzero verified frame count. This covers canonical linter revisions whose
numeric-filename discovery skips sequence-plus-hash frame filenames, without
copying/renaming frames or implementing another protocol verifier.

This public repository contains reusable tools, synthetic fixtures and tests
only. Actual profile roots, selected rosters, provider IDs, generated registries,
dashboards, identities and editor views stay private. No push/merge/publication
or live native-store mutation is part of local manager operations.

## 11. Frame Anything: closed Workspace/1 control sidecar

**RAPP-valid != accurately observed != semantically faithful != currently
authorized != safely deployable.**

Workspace/1 is a safe local seed/control-plane and deterministic projection host.
The expected core spec/manifest pins and exact parent commit are defined
in `tools/workspace1_runtime.py` and printed by `workspace1 contract`. The canonical
protocol is `rapp-workspace/1`, branding **RAPP Workspace/1**.
The `rapp/1` eleven-key frame envelope remains unchanged. All Workspace/1 records
MUST be built/verified by the explicitly supplied pinned canonical parent,
using the canonical reference payload schemas and `body.pulse` stream.

The existing registry schema, manager RAPPID, routing world, pointer identities,
suppression, organization and owner order MUST NOT change merely by binding,
initializing, observing, running a lens, staging, adopting or projecting Workspace/1
data. Existing legacy commands remain backward compatible. Workspace/1 MUST NOT
invoke native discovery, providers or routed-source adapters.
An existing manager-root `frames` location MUST refuse unqualified root-stream
reuse rather than starting another sequence-zero chain. Separate legacy
project streams remain untouched; externally located root streams require an
independent owner checkpoint/qualification, not discovery or automatic grafting.

The manager-owned private `.workspace1/` directory contains:

| File | Role |
|---|---|
| `binding.json` | Closed `rapp-workspace-manager/workspace1-binding/1`: version, exact protocol contract, explicit checkout/parent locators and filesystem identities, public image checksum and complete file closure, existing manager RAPPID/world. Immutable binding, not source authority. |
| `runtime-image.json` | Closed `rapp-workspace-manager/workspace1-image/1`: exact verified public bytes, encoded as data. No importable modules, instructions or plugins are generated. |
| `policy.json` | Closed `rapp-workspace-manager/workspace1-policy/1`: independent external-host rights/scopes, sequence, expiry and root budgets, bound to the existing manager identity/world and checked against canonical controller policy. |
| `controller/controller.sqlite3` | Canonical local controller ledger/frames/receipts/heads/suppression/faults. One closed `manager_state` metadata value joins its transaction domain; it is not a replacement routing or task store. |
| `state.json` | Disposable mirror of `manager_state`. It MUST NOT be loaded as effective grants or an adoption fallback. |
| `view.json`, `view.md`, `estate.code-workspace` | Fixed, deterministic, inert manager projections. No source/native folders are added. |

`manager_state` has exactly:

```text
schema version spec_id manager_rappid world_id binding_sha256
seed_lineage adopted_projection_head frontier manager_frontier
jobs stages projections checkpoint
```

`schema` is `rapp-workspace-manager/workspace1-state/1`, `version` is integer 1.
`seed_lineage` contains exactly one canonical seed wave, reused on restart.
No identity is minted for an existing manager. Missing/corrupt authoritative
state, unknown keys/types/versions or mismatched identity/world MUST refuse.
There is no automatic state reinitialization or recovery from graph-shaped
adoption/authority claims.

The `frontier` is the complete canonical controller frontier: instance/world,
policy, graph/adoption/routing heads, suppression, source bindings, runtime
commitment and sequence. `manager_frontier` contains exactly SHA-256
measurements of registry bytes, identity bytes, routing metadata, suppressions,
organization, worlds, external policy bytes and binding bytes. These are
manager CAS/file checksums, not new RAPP identities or hash domains.

Each bounded job has exactly:

```text
id subject form source observations attempts receipts outcome reason
plan feedback migration capture_frontier
```

These are references to framing work, not a copied task backlog. Observations,
lenses, attempts, refusals and exhaust remain canonical frames. Each attempt
has `lens,result,kind,reason`; a pre-lens root stop has null `lens`. `receipts`
has exactly the five named guarantees. Receipts bind canonical subject,
instance/world, exact validator/runtime pins, scope/method/evidence and
restrictions. A recorded verified state MUST NOT become a capability.
`feedback`, when present, has `refusal,exhaust,source` wave references.
Plans are closed `identity|adaptive|strict-field` selections and an exact
field, never executable programs. A job's plan cannot be silently changed.

Migration metadata is exactly `registry_sha256,unresolved,worlds,
behavior_coverage,routes_changed`, with `registry-metadata-only` coverage and
`routes_changed:false`. Each stage has exactly `job,request,protocol_frontier,
manager_frontier,token,contract,status,record`. Projection metadata is exactly
`generation,focus,files,authority,native_routes`; both authority/native routes
are false. Files have only name/checksum/byte count. The controller checkpoint
retains its canonical complete frame/frontier/fault/suppression/adoption proof.

## 12. Closed observation, lens, rights and adoption boundary

`workspace1 bind` MUST accept only explicit absolute protocol/parent checkouts,
verify exact expected manifest/spec/index/closure/parent bytes and filesystem
identities, and use no network discovery, home search or historical fallback.
Current and historical validator IDs MUST NOT be conflated. Captured public
code, schemas and parent provenance MUST be the same bytes consumed by the
loader/validator; candidate evaluators get no ambient imports, environment,
network, credentials, callbacks or host tools. Every fresh execution MUST
requalify the entire current pinned runtime closure. Retained public history
bytes do not qualify fresh execution.

External rights for capture, retention, local synthesis, adoption and
materialization MUST remain independent and outside learned/received graphs.
Each effectful CLI action also requires its corresponding explicit flags.
The live CLI supplies trusted current UTC and enforces the durable clock
floor/expiry, never taking current time from fixture data. An immutable
existing policy cannot be widened, rebound or used to reset budgets by rerunning
`init`; policy transitions not implemented by this host MUST refuse.

Capture forms are:

1. `supplied-octets`: finite explicitly supplied immutable bytes, no source path.
2. `file-octets`: an exact approved synthetic regular-file fixture read through
   canonical bounded no-follow stable-descriptor I/O, never claiming coherence.
3. `directory-metadata-fixture`: an explicitly approved synthetic one-level
   enumeration of names/types/file sizes only. No child contents/descendants
   are read. Its immutable assembled buffer states `one-level-metadata-not-coherent`.
4. `registry-metadata`: only existing manager-registry bytes/normalized metadata,
   with no routed-source access.

Authorization, retention and remaining source-access budgets MUST be checked
before fixture stat/enumeration/open/decode. Filesystem fixtures additionally
require `--synthetic-fixture`; they are not native adapters. Scope/path/form
substitution, links, hardlinks, credentials/native names, special files,
registered native protection identities or controller/tooling overlap refuse.
Scope attestation MUST NOT be misrepresented as a universal secret detector.
File/directory fixtures and their descendants inherit adoption denial; a
fallback MUST NOT launder them into supplied-octet/native adoption.

Opaque invalid bytes may be observed but strict JSON interpretation MUST
refuse invalid UTF-8, duplicates, huge/out-of-domain numbers, unsupported
structures and undeclared reads. The canonical total evaluator supports
bounded `identity-octets` and exact `json-field` only. Actual, necessary,
synthesis, enumeration, negative and environment reads retain their distinct
meaning. Replay equality is not fidelity.

`adaptive` runs lens A, retains its refusal and repeated-state exhaust, and
captures a finite context containing the original bytes plus the exact
refusal/exhaust. B consumes that context through the canonical identity lens,
intersecting all restrictions and using the same root budget. This is not
learning native semantics. Feedback refusal/exhaust MUST remain retained even
if B's context exceeds budget. Strict-field refusal is a valid stable outcome.
Repeated job runs reuse the same plan/result; root stops are durable.

`workspace1 stage` requires independent host approval of the exact complete
captured-byte identity/inverse contract. Partial JSON-field coverage MUST NOT
be upgraded to full fidelity. Staging emits request data only.

`workspace1 adopt` requires a separate external action grant and the exact stage
token. The existing manager lock and canonical controller lock enforce one
local writer. Canonical adoption/authorization receipts, decision ledger,
heads, manager state and checkpoint MUST commit together in one SQLite
transaction; nested canonical operations use savepoints. COMMIT is the
linearization point. The complete canonical and manager frontiers MUST match,
including suppression, source occurrence, world, policy, runtime and exact
registry bytes. A final manager CAS precedes COMMIT. Crash-before-commit
rolls back all decision state; lost acknowledgements return the exact existing
record. Changed operation content refuses. An acknowledgement is historical
evidence, not renewed authority for materialization or future action.
Manager accepted-stage records MUST exactly match canonical controller
operation/request/candidate/record tuples. Missing or inconsistent manager
decision metadata MUST quarantine instead of becoming a cache/graph recovery
path for effective authority.

Native-subject suppression survives new content and occurrence waves.
Verified owned-store forks latch refusal across restart. Local unsigned
faults MUST NOT be called signed owner equivocation. Distributed/controller
merge, partitioned effects and self-authenticated whole-store rollback are
not implemented. Independent monotonic checkpoints remain a hosting gate.

## 13. Inert projections, metadata migration and limits

Workspace/1 materializes captured byte values only from accepted views with current
separate retention/materialization rights and inherited restrictions.
Assurance metadata may additionally show unadopted jobs and safe refusals,
including in a focused view; this MUST NOT adopt their byte values. Its JSON
is data only; raw source text stays encoded. Markdown contains fixed explanatory text
and escaped assurance metadata, never source instructions or active links.
The editor view contains the manager once using the fixed relative `..` root,
no native/source routes, tasks, hooks, plugins or extension recommendations.
No untrusted strings are interpolated into commands or executable files.
HTML, remote images/links, instruction files and executable permissions MUST
NOT be generated from captures or projections.

Only `.workspace1/view.json`, `.workspace1/view.md` and
`.workspace1/estate.code-workspace` are Workspace/1 projection destinations. There is no
arbitrary output-path option or external/public export. Existing routing
registry/editor files and settings remain unchanged. Committed checksums/focus
precede individually atomic projection writes. After a crash, inspect exposes
staleness; authorized `recover` regenerates from controller state, never from
the cache. Changed manager/suppression frontiers refuse stale materialization.
A fresh explicitly focused job may exclude stale historical adoptions without
resetting the seed. The default all-job view MUST refuse any included stale adoption.
Without materialization permission recovery only repairs the state mirror.

`workspace1 history` verifies nonzero RAPP/1 frames using retained pinned public
validator data even if the current evaluator is unavailable. Current retention
rights and monotonic time remain required. Other guarantees are historical or
unavailable, not freshly authorized. RAPP integrity alone is never deployment
or permission.

`workspace1 migrate --metadata-only` MUST preserve original registry bytes,
RAPPID/worlds, pointer/native identity, owner order, organization and complete
suppression metadata. It MUST NOT stat, read, index, upgrade or rebind routed
paths. V1 pointers lacking filesystem identity, missing selected-native
references and incomplete partitions remain unresolved and cannot be adopted.
Only an independently approved explicit safe re-add may verify a local root;
a new observation is then required. Old observations are never rewritten.
Even complete V2 metadata can produce only an inert metadata view, not a
behavior-preserving or coherent native migration. A fresh stage cannot repair
a stale captured registry frontier.

Bounds: 32 scopes/jobs (plus reserved seed/registry scopes), 32 stages, 64 KiB
per capture, one-level directory maximum 128 entries and ten-second cooperative
deadline, 1 MiB manager state and each projection, and the canonical root
budget defaults/ceilings (8/128 attempts, 4/32 depth, 256/512 frames,
1 MiB/64 MiB aggregate capture). The public closure is bounded to 64 files/
4 MiB. No partial migration or zero-artifact conformance may be called complete.

Hosted model calls, arbitrary code/imports, automatic native grafts/rebinding,
live native migration, coherent database snapshots, partitioned/external
effects, public export, unqualified runtimes, timed physical erasure and
fabricated learned-semantic claims MUST remain explicit refusals.

The exact CLI/scope schema, public one-command demo, integration/unchanged
canonical P0/P1 tests, read-only-input cross-repo conformance and private
shadow/live-pilot blockers are documented in `docs/frame-anything.md`.
Public tests/COMPLIANT integrity do not constitute signed activation or
authorization to start a private shadow or live native pilot.
