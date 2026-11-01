# Roadmap Phases I–III: implementation and acceptance

Scope: unfinished implementation in root ROADMAP Phases I, II and III, following
their stabilization order. Baseline: `89f2c2b`. Contribution branch:
`codex/complete-phases-i-iii`, [PR #9](https://github.com/Praxis1071/NetFather/pull/9).
Linux-only; the normal GTK process remains unprivileged.

## Phase I — network truth

- Reviewed identity aliases retain the selected device ID. Randomized-MAC
  candidates require matching metadata and non-overlapping observations. A locally
  administered MAC is a possibility of randomization, not proof. Names/vendors
  never cause automatic identity merges. Explicit physical verification is required.
- Merge refuses concurrent online identities, unresolved conflicts and candidate
  policies/assignments. Split creates a separate offline device without cloning
  policies; retained enforcement requires review. Operations are audited.
- Conflicting address claims remain separate and cannot become enforcement targets.
  Confidence describes discovery evidence, not authenticated physical identity.
- Confirmed IPv4/IPv6 paths and interfaces survive restart. IPv4 is preferred for
  the selected target while this backend remains IPv4-oriented. Unscoped link-local
  IPv6 is excluded from enforcement. Changed Nmap port/service snapshots persist.
- Optional unexpired DHCP leases and bounded local mDNS/LLMNR/NetBIOS queries enrich
  observations; they do not prove presence. Asynchronous libnm state signals request
  reconciliation. Missing optional tools leave periodic discovery usable.
- Domain events publish only after commit. Rollbacks publish nothing, subscriber
  errors are isolated, and GTK consumers dispatch through GLib.
- Cancellation before the persistence boundary preserves device state. Ordinary
  children are terminated/reaped cooperatively. Elevated Nmap runs inside a
  privileged GNU timeout guardian: when a UID change prevents immediate signaling,
  cancellation waits for bounded cleanup. Default budget: 300 seconds, maximum 600,
  plus a two-second forced-termination grace. GUI root execution is unnecessary.

Acceptance: `test_phase_one_core.py`, `test_discovery_adapters.py`, service/SQLite
tests and `integration/test_presence_netns.py`. The namespace test uses real
IPv4/IPv6 kernel notifications, aging, shutdown and restart. Five jobs passed in
[CI 41345917657](https://github.com/Praxis1071/NetFather/actions/runs/41345917657)
before Phase II implementation began.

## Phase II — GTK product

- Libadwaita application/window, native appearance, adaptive navigation, keyboard
  workspace actions and narrow layouts. Native labeled controls and text statuses
  accompany semantic colors.
- Page task scopes suppress callbacks after close and cancel pending work. Live
  presence lifecycle changes run in serialized workers. Late asynchronous
  NetworkManager initialization cannot reattach after stop.
- Device details include metadata editing, source/confidence, address/MAC history,
  services, profiles, desired policy, actual/unverified kernel state and events.
  Forget, identity and policy operations have explicit confirmations.
- Discovery exposes stages, cancellation, capability/authorization warnings, deep
  findings and durable history. Events refresh from committed transitions.
- Topology distinguishes observed interfaces, bridge ports, VLAN parents and
  wireless peers. AP/client roles require observed AP mode. Transit is inferred;
  unsupported attachment remains unknown.
- Nine workspaces render in English/Turkish/Azerbaijani at 360/620/1240 widths,
  in light/dark/system appearances and native high contrast. The `gtk-workspaces`
  artifact contains ordinary/high-contrast screenshots for visual review.

Acceptance: `integration/test_gtk_workspaces.py`, callback/lifecycle tests and
`test_topology_evidence.py`. Six jobs passed in
[CI 41346588305](https://github.com/Praxis1071/NetFather/actions/runs/41346588305)
before Phase III began. Desktop, narrow and high-contrast screenshots were
inspected. This is a Linux/Xvfb baseline, not validation on every desktop or
screen reader.

## Phase III — profiles and deterministic policy

- Reusable profiles support editing/mode changes, explicit assignment/unassignment,
  history and deletion guards. Existing device-bound profiles remain active,
  visible and editable; assigning a reusable group does not erase old policies.
- Device/profile rules support CRUD, enable/disable, priorities, multiple windows,
  weekdays and IANA time zones. Policy reads use one database snapshot and instant.
- Blocked profile > active block > active allow > controlled default deny.
  Priority chooses within an action; scope and persistent ID break ties stably.
- Overnight windows belong to their starting weekday. UTC evaluation covers DST
  gaps and both repeated folds. Effective next transitions skip irrelevant changes.
- Shared-scope conflict previews cover the next eight days, recomputed as time
  advances. Device explanations include active inherited/device conflicts.
  Invalid enabled legacy rules require review.
- Whole-device policies are supported. Service/port/destination selectors are
  explicitly rejected until Phase IV supports their kernel enforcement.
- Stored naive UTC event timestamps render correctly in local time. Additive,
  idempotent migration retains old rules and their behavior.

Acceptance: `test_phase_three_policy.py`, existing profile/rule/policy tests and
actual GTK device/profile/rule CRUD, confirmations and assignment flows. Six jobs
passed for `ca01ef8` in
[CI 41347465925](https://github.com/Praxis1071/NetFather/actions/runs/41347465925):
Python 3.12/3.13/3.14, editable installation, three privileged namespace tests and
ordinary/high-contrast graphical scenarios. Follow-up lifecycle, guardian, UTC
and migration changes require fresh head CI before merge.

## Verification and authority

Windows/Python 3.13.5 retains five pre-existing Linux-specific failures:
permissions/geteuid and Windows paths in TOML fixtures. Supported Linux CI is
authoritative. Compilation, version consistency and diff checks also pass.

Implementation and stabilization evidence do not grant release or Phase IV
approval on behalf of the project owner. The final Gate III transition checkbox
is reserved for maintainer PR review. This contribution performs no merge or
enforcement-phase rollout.
