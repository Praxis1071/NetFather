# NetFather Technical Debt and Fix Plan

This document records the repository-wide engineering findings from the September 2026 review. It is the source-of-truth checklist for the current hardening cycle.

Status markers:
- [x] fixed in the current main branch
- [ ] open
- [~] partially implemented / needs follow-up

## P0 — correctness and safety

### P0.1 CI enforcement integration failure
- [ ] Identify and fix the failing nftables network-namespace integration job.
- [ ] Re-run the complete CI matrix.
- [ ] Do not treat unit-test success as sufficient for firewall correctness.

### P0.2 Linux-only diagnostics compatibility
- [x] Remove the stale PlatformFamily dependency and Windows/macOS branches from core/diagnostics.py.
- [ ] Add a regression test that imports and executes diagnostics on Linux.

### P0.3 Enforcement deployment model
- [ ] Document and enforce the supported topology for controlling other devices.
- [ ] Distinguish a NetFather desktop host from a Linux gateway/router or other valid traffic enforcement point.
- [ ] Prevent the UI from implying that discovering a device automatically gives NetFather control over its internet traffic.

### P0.4 Effective profile semantics
- [ ] Define and implement the meaning of unrestricted, controlled, and blocked.
- [ ] Ensure controlled produces a real policy outcome rather than falling through to default allow.
- [ ] Add policy precedence tests.

### P0.5 Enforcement identity
- [ ] Stop treating a current IPv4 address as the durable identity of a device.
- [ ] Connect persistent device identity/history to enforcement targets.
- [ ] Update enforcement safely when DHCP changes a device IP.

### P0.6 Self-lockout protection
- [ ] Protect the NetFather host/management path before applying blocking policies.
- [ ] Add explicit gateway/interface/admin-host safeguards.
- [ ] Integration-test failure and recovery paths.

### P0.7 Privileged-service separation
- [ ] Design a narrowly scoped Linux D-Bus service.
- [ ] Add polkit authorization for only the operations that require privilege.
- [ ] Keep the GTK process unprivileged.

## P1 — core network architecture

### P1.1 Persistent identity
- [ ] Persist MAC/IP history, identity observations, confidence, and discovery sources.
- [ ] Preserve identity across application restarts.
- [ ] Account for randomized Wi-Fi MAC addresses where evidence permits.

### P1.2 Live presence and event propagation
- [ ] Turn neighbor events into direct device state transitions where safe.
- [ ] Add a central runtime event bus.
- [ ] Emit and persist NEW_DEVICE_DETECTED, DEVICE_ONLINE, DEVICE_OFFLINE, DEVICE_CHANGED, DEVICE_IDENTITY_UPDATED, and policy/enforcement events consistently.
- [ ] Keep the periodic discovery scan as a safety reconciliation mechanism rather than the only event path.

### P1.3 Atomic nftables updates
- [ ] Replace destructive table recreation with atomic named-set element updates.
- [ ] Preserve counters and unrelated NetFather state across policy changes.
- [ ] Keep rollback behavior explicit and testable.

### P1.4 Existing-flow handling
- [ ] Define conntrack behavior for policy changes.
- [ ] Test transitions from allowed to blocked and blocked to allowed with existing connections.

### P1.5 Discovery configuration correctness
- [x] DiscoveryService.scan() now accepts auto_register and offline_after_seconds.
- [ ] Pass those values from application configuration everywhere discovery is invoked, including live presence.
- [ ] Add tests proving configuration changes alter reconciliation behavior.

### P1.6 Deep inventory
- [ ] Use host discovery to bound deep scans before expensive TCP/UDP/version/OS probes.
- [ ] Avoid broad -Pn scans over large local subnets by default.
- [ ] Surface skipped capabilities and warnings in DiscoverySnapshot and the GUI.
- [ ] Keep deep inventory local-network bounded and free of default NSE scripts.

### P1.7 Additional discovery sources
- [ ] IPv6/NDP.
- [ ] DHCP lease information.
- [ ] NetworkManager device/connection signals.
- [ ] mDNS/LLMNR/NetBIOS enrichment where appropriate.
- [ ] Persistent service/port history.

## P2 — product completeness

### P2.1 Profiles UI
- [ ] Complete profile edit, mode change, and delete workflows.

### P2.2 Rules UI
- [ ] Complete rule enable/disable, edit, and delete workflows.
- [ ] Make schedule semantics explicit, including overnight schedules.

### P2.3 Monitoring
- [ ] Add device-level traffic accounting.
- [ ] Prefer nftables/tc/conntrack/interface counters over continuous Python packet sniffing for normal telemetry.

### P2.4 Topology
- [ ] Keep logical topology honest.
- [ ] Add real interface/AP/switch/bridge/VLAN relationships only when backed by observations.

### P2.5 GUI architecture
- [ ] Finish Libadwaita migration where useful.
- [ ] Improve adaptive navigation and narrow-window layouts.
- [ ] Centralize page lifecycle/disposal and timer cleanup.
- [ ] Remove duplicate/dead GTK page implementations.

### P2.6 Test coverage
- [ ] Add live-presence integration tests.
- [ ] Add deep-scan subprocess/error-path tests.
- [ ] Add policy-to-firewall end-to-end tests.
- [ ] Add GTK state/background-task lifecycle tests.

## P3 — repository and release hygiene

### P3.1 Linux-only cleanup
- [ ] Remove stale Windows/macOS runtime/documentation references that contradict the current project direction.
- [ ] Remove stale CLI/TUI architecture documentation.

### P3.2 Metadata consistency
- [x] Correct the Python package license classifier to GPL-3.0-or-later.
- [ ] Keep README, LICENSE, pyproject metadata, release docs, and version information synchronized.

### P3.3 Release pipeline
- [ ] Decide whether ARM64 is a supported release target.
- [ ] If supported, build it on an ARM64 runner rather than merely renaming an x64 artifact.
- [ ] Validate GTK4/PyGObject/native-library packaging before publishing release artifacts.

## Completed in this hardening pass

- Created a pre-fix backup branch: backup/pre-p0-fixes-2026-09-23.
- Updated README.md to state the current implementation boundary and link this checklist.
- Rewrote SECURITY.md around the actual Linux-only architecture and current enforcement limitations.
- Removed the broken cross-platform PlatformFamily dependency from core/diagnostics.py.
- Corrected the GPL license classifier in pyproject.toml.
- Made DiscoveryService accept explicit auto-registration and offline-grace settings instead of hard-coding them.

This file should be updated whenever a finding is fixed, superseded, or split into smaller engineering tasks.
