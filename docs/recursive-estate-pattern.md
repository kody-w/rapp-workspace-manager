# Recursive estate organization pattern

**Legacy routing workflow.** Start new Grail work with
[Frame Anything](frame-anything.md). The Grail sidecar can observe this
organization metadata without visiting sources, but does not authorize the
legacy pilot/route changes below. Grail native migration/rebinding and live
effects remain disabled; its focused editor view is manager-only.

Use this pattern to reduce editor-root sprawl without moving, nesting, reading
or re-identifying source workspaces.

## Delivery boundary

- Keep `rapp-workspace-manager/1`; use only its local `organization` version 1
  overlay.
- Keep the manager first in every editor view. It is a routing root, not a
  container.
- Group selected local pointer IDs only. Do not copy content, infer tasks,
  create identities or flatten native-provider metadata.
- Use synthetic fixtures for public testing. Private paths, pointer IDs,
  aliases, registries and generated views remain in the private manager.

## Pilot sequence

1. Confirm the existing all-selected `editor-view` is healthy.
2. Add a small root-level taxonomy, then add child groups only where a focused
   view has a clear owner purpose.
3. Assign selected local pointers explicitly. Use short aliases only when they
   improve routing; allow unassigned pointers to remain visible under
   `Unorganized`.
4. Review `tree`, then create one deterministic `focus` view per active work
   context.
5. Re-run exact and recursive scans in a synthetic rehearsal. Confirm retained
   pointers keep placement and removed pointers produce manager-only stale
   focus views.
6. Validate manager-first ordering, source-byte non-mutation, JSON/JSONC owner
   settings, full tests and repository conformance before wider use.

Microsoft CEO may be used as a **private pilot example only**. Do not publish
that pilot's paths, pointer IDs, aliases, registry, dashboard or focused views.

## Operations and rollback

Use `group unassign` before removing a populated group. Root removal is always
refused. A clear/forget or rescan that removes a pointer also removes its active
alias and placement; re-add requires a new explicit assignment.

Rollback is manager-only: unassign placements, remove empty groups and continue
using the unchanged all-selected `editor-view`. No source or native-provider
rollback is needed because the overlay never mutates them.

## Pilot measures

Measure only manager metadata: selected-pointer count, organized versus
unorganized count, group depth, focused-view count, ambiguity refusals and
successful regeneration. Do not inspect or index routed workspace content.
