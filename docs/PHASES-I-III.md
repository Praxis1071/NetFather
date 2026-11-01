# Roadmap Phases I–III implementation and acceptance

Requested scope: all unfinished tasks in root ROADMAP Phases I, II and III,
including each stabilization gate. Baseline: `89f2c2b`. Work is isolated on
`codex/complete-phases-i-iii`; the project remains Linux-only and GTK4-native.

## Phase I — network truth

Implemented in the first slice:

- Conservative randomized-MAC candidates and explicit, audited identity merge,
  split and conflict review. Names/vendors never cause automatic identity merges.
- Stable retained IDs and reviewed MAC aliases; policies never copy silently.
- Conflicting address claims remain separate and cannot become enforcement targets.
- Retain confirmed IPv4/IPv6 addresses and interfaces; prefer IPv4 as the selected
  address while the enforcement backend remains IPv4-oriented. Link-local IPv6
  addresses retain interface context and are not promoted to remote enforcement.
- Persist changed Nmap port/service snapshots independently of identity metadata.
- Optional unexpired DHCP lease enrichment, bounded system mDNS/LLMNR queries and
  NetBIOS fallback for already observed local hosts; these are metadata, not proof
  of presence. Missing optional tools do not invalidate successful observations.
- Optional libnm device/connection/config signals debounce through the same live
  reconciliation path. Missing NetworkManager leaves periodic discovery available.
- Cooperative scan cancellation, bounded cancellable subprocesses and a defined
  commit boundary. Cancellation before persistence preserves device state.
- Per-database committed event bus and canonical event names; callbacks are
  isolated and UI delivery is dispatched to GLib. Rollbacks publish no events.
- Durable scan outcomes and application-owned observer cleanup.

Acceptance evidence: controlled service/SQLite and adapter tests; a privileged
Linux test exercises actual IPv4/IPv6 neighbor notifications, discovery, cache
aging, monitor shutdown and restart with durable history. Fresh CI is required
before the phase gate can close. CI run 41345917657 now passes all five jobs, including the new real kernel test (three privileged tests passed). The Windows baseline's five Linux-specific
test failures are recorded separately from supported Linux results.

## Phase II — GTK product completion

Implemented after Gate I; graphical CI verification is in progress: Libadwaita adaptive shell and workspace layouts; scoped
background tasks, cancellation and lifecycle-safe delivery; consistent states
and confirmations; complete device evidence/policy/history details; discovery
progress/capabilities/history; observed/inferred/unknown topology relationships;
keyboard/accessibility, appearance and language QA under a supported GTK session.

## Phase III — reusable profiles and deterministic policy

Pending after Gate II: reusable groups and explicit device assignments; complete
profile/rule CRUD and audit history; priority, allow/block/default-deny semantics;
multiple/overnight windows, timezone handling, conflicts, explanation and next
transition; safe handling of unsupported traffic selectors; integration and
failure-path verification before the enforcement phase.

## Verification discipline

The root ROADMAP remains authoritative. Checkboxes represent verified behavior,
not merely the presence of code. Record CI and graphical evidence here as each
slice passes; never infer that an unavailable capability was tested successfully.
