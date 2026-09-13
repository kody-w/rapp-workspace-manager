# RAPP Workspace Manager Profile

`spec_id: rapp-workspace-manager/1`

An application of `rapp/1` identity/frames and the manager rule in
`rapp-workspace/1.1`. This extension adds routing pointers, not a new protocol
or a unified native AI storage model.

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
- `forgotten`: local pointer identifier tombstones.
- `editor_view`: primary manager-owned `.code-workspace` filename.
- `editor_views`: bounded list of generated filenames, all regenerated on
  pointer changes so obsolete views do not retain forgotten routes.

Legacy local registries load without reminting identity. Missing extension
fields and local pointer discriminators are upgraded in memory; the next
explicit mutation persists the extension. Unknown fields, types, versions,
providers, cross-partition identities and world/manager mismatches fail closed.

Every local pointer has `pointer_version: 1`, `pointer_type: local-directory`,
a deterministic `pointer_id`, `selection: exact|discovered`, and only:
`name,path,kind,rappid,mode,world_id,tags`. `path` is absolute, `kind` is
`directory|git|rapp-workspace`. RAPP labels require canonical validation of a
bounded root `rappid.json`; symlinked or invalid identities are ignored.

Every native pointer has `pointer_version: 1`, `pointer_type`, `pointer_id`,
`provider`, and `profileRoot`, followed by exactly one provider-specific shape:

| Discriminator | Provider-specific fields |
|---|---|
| `copilot-session` | `nativeSessionId`, `metadata` (only the nine allowlisted workspace.yaml fields), `sourceStamp`, `availability: metadata|missing-metadata` |
| `claude-project` | `nativeRoot`, `nativeKey`, `indexVersion: 1|null`, `originalPath`, `pathAssociations` (distinct originalPath/projectPath pairs), `availability: indexed|missing-index` |
| `hermes-session` / `hermes-project` / `hermes-folder` | `nativeTable`, `nativeId` (native string/integer type retained), `schemaVersion: 0`, provider-native allowlisted `metadata` columns |
| `scout-workspace` | `nativeVersion: 3`, `workspaceId`, `providerId`, `rootId` |

There is deliberately **no Grokbot workspace pointer discriminator**.
Grokbot observations contain only `provider,profileRoot,state,mapping,observation_id`, with
`state: app-detected`, `mapping: workspace-mapping-unavailable`.
The observation key is manager-owned, derived from the profile root, and
supports suppression; it is not an invented native bot/workspace ID.

Pointer keys are SHA-256 over a JSON tuple of provider, absolute profile root,
native discriminator and native identity. They are manager routing keys, not
RAPPIDs, a new protocol hash contract, or evidence of trust. Copilot uses the
native session UUID; Claude uses the untouched bucket key beneath the native
projects root; Hermes uses `[nativeTable, nativeId]`; Scout uses workspace ID.
The original native fields remain available. No provider's shape is flattened
into another provider's model.

## 3. Provider partitions, selection and failure

Each provider partition contains exactly:

- `profileRoots`: the last successfully committed profile set;
- `requestedRoots`: the explicitly requested refresh profile set;
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
plain/quoted/null scalars; complex YAML for allowlisted fields fails closed.
Unknown content-bearing fields are not retained or interpreted.

Use a bounded one-level inventory and metadata batches. A checkpoint includes
inventory directory stat fingerprints, native UUID names, offset and staged
allowlisted pointers. Incomplete staged candidates are never active routes.
Revalidate membership stamps on resume/completion. Reuse a prior metadata
pointer only when its no-follow file stat fingerprint is unchanged. Missing
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
native candidate. `forget` additionally persists an identifier-only tombstone
until explicit `re-add`. Clear-cache MUST NOT remove tombstones. Forgetting a
whole known catalog does not suppress future unknown native identities.
Re-add does not fabricate native data: a suppressed native ID remains pending
rediscovery before it can resolve locally.

Clear/forget discard in-progress provider staging, preserve other partitions,
and regenerate all tracked manager views. No source identity or history is
rewritten. A duplicate local name MUST fail closed during open/resolve.

Grokbot observation IDs support clear/forget/re-add with the same durable
tombstones, but can never enter `selected` or become editor roots. Re-add of
an observation only enables later rediscovery; it never invents a mapping.

## 7. Safe deterministic projections

The editor view contains the manager first, then selected local entries in
owner order, then explicitly selected native references in deterministic
provider/identifier/path order. Dedupe exact filesystem paths for the view
only; never collapse native identities. A Claude selection can contribute
multiple verified local associations. Copilot uses explicit cwd, otherwise
explicit git_root; Hermes sessions without cwd stay unknown.

Only existing absolute no-follow local directories are folders. Unknown,
missing, protected and nonlocal references remain visible in the dashboard/
catalog. Native roots are never converted to filesystem paths by guessing.

Editor output filenames MUST be direct children of the private manager and
end in `.code-workspace`. Preserve unrelated JSON/JSONC settings, extensions
and top-level values; replace only `folders`. Comments/formatting need not
survive. Corrupt/unsafe outputs fail closed. The dashboard renders escaped
metadata only and caps its native preview at 100 candidates per provider.

Writes use exclusive same-directory staging, flush/fsync, atomic replace and
directory fsync; manager output symlinks are refused. Registry and projections
are each atomic, **not a multi-file transaction**. Registry is committed first;
after a crash regenerate projections from it. Retained editor filenames ensure
that previously generated views can also be rebuilt after clear/forget.

## 8. Bounds

Default/hard scan limits: entries 150,000/200,000; Copilot metadata batch
1,000/10,000; individual metadata file 2/8 MiB; per-invocation metadata bytes
16/64 MiB; cooperative deadline 10/60 seconds. Count ignored entries too.

Fixed limits: 16 provider roots, 128 scan/exact roots, recursive depth 64,
128 lexical path components, 4 KiB strings, 32 root routing tags, 64 KiB root
RAPP identity file, 128 MiB compact provider catalog/stage, 512 MiB manager
registry, 16 editor views, 8 MiB existing editor file, 2 GiB Hermes database
stat size. Editor folder resolution allows 10,000 folders and a 10-second
cooperative verification deadline. Checks include regular-file types, no-follow ancestors/leaves,
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
  `estate`, `scan --mode recursive|exact`, `editor-view`, and local
  `list|open|clear|clear-cache|forget|re-add`.

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
