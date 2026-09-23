# NetFather Technical Debt and Fix Plan

This document records the repository-wide engineering findings from the September 2026 review. It is the source-of-truth checklist for the current hardening cycle.

Status markers:
- [x] fixed in the current main branch
- [ ] open
- [~] partially implemented / needs follow-up

## P0 — correctness and safety

### P0.1 CI enforcement integration failure
- [x] Root cause identified: the generated nftables base-chain rules were missing statement terminators before closing braces, so nft rejected the ruleset in the namespace integration test.
- [x] Corrected the nftables ruleset generator to emit valid multi-line chain syntax.
- [x] Added an explicit privileged prerequisite probe and verbose test output so runner failures remain diagnosable.
- [x] Confirmed the corrected ruleset with green CI runs 126 and 127 on the main branch.
- [ ] Do not treat unit-test success as sufficient for firewall correctness.

### P0.2 Linux-only diagnostics compatibility
- [x] Remove the stale PlatformFamily dependency and Windows/macOS branches from core/diagnostics.py.
- [x] Add a regression test that imports and executes diagnostics on Linux.

### P0.3 Enforcement deployment model
- [x] Document that discovery does not imply remote traffic control.
- [x] Document the required gateway/router/inline traffic path for controlling another device.
- [ ] Add runtime validation and UI safeguards so the deployment topology is explicit before enforcement.

### P0.4 Effective profile semantics
- [x] Define unrestricted, controlled, and blocked semantics in PolicyEngine.
- [x] controlled now denies by default and requires an active allow rule.
- [x] An active block rule overrides an active allow rule.
- [x] Add policy precedence tests.

### P0.5 Enforcement identity
- [ ] Stop treating a current IPv4 address as the durable identity of a device.
- [ ] Connect persistent device identity/history to enforcement targets.
- [ ] Update enforcement safely when DHCP changes a device IP.

### P0.6 Self-lockout protection
- [~] Firewall sync now refuses to install blocks for the detected local IPv4 address or gateway IPv4 address.
- [ ] Add explicit interface/admin-host safeguards beyond the basic local/gateway guard.
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
- [~] Linux neighbor notifications are already monitored and debounced.
- [~] Current presence events trigger discovery reconciliation.
- [ ] Turn safe neighbor events into direct device state transitions.
- [ ] Add a central runtime event bus.
- [ ] Emit and persist NEW_DEVICE_DETECTED, DEVICE_ONLINE, DEVICE_OFFLINE, DEVICE_CHANGED, DEVICE_IDENTITY_UPDATED, and policy/enforcement events consistently.
- [ ] Keep periodic discovery as a safety reconciliation mechanism.

### P1.3 Atomic nftables updates
- [ ] Replace destructive table recreation with atomic named-set element updates.
- [ ] Preserve counters and unrelated NetFather state across policy changes.
- [ ] Keep rollback behavior explicit and testable.

### P1.4 Existing-flow handling
- [ ] Define conntrack behavior for policy changes.
- [ ] Test transitions from allowed to blocked and blocked to allowed with existing connections.

### P1.5 Discovery configuration correctness
- [x] DiscoveryService.scan() accepts explicit auto-registration and offline-grace settings.
- [x] LivePresenceService receives and uses those settings.
- [ ] Add broader tests proving configuration changes alter reconciliation behavior.

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

### P3.4 Developer installation / venv reproducibility
- [x] Document the supported CachyOS/Arch Linux setup using a Python venv with `--system-site-packages` so distribution-provided GTK4/PyGObject can be reused safely.
- [x] Document editable installation with `python -m pip install -e .` and repeatable launch through the `netfather` entry point.
- [x] Remove duplicate runtime dependencies from `requirements-dev.txt`.
- [ ] Add CI coverage for the documented editable-install workflow and entry-point launch contract.

### P3.3 Release pipeline
- [ ] Decide whether ARM64 is a supported release target.
- [ ] If supported, build it on an ARM64 runner rather than merely renaming an x64 artifact.
- [ ] Validate GTK4/PyGObject/native-library packaging before publishing release artifacts.

## Completed in this hardening pass

- Created backup branch: backup/pre-audit-fixes-2026-09-23.
- Updated README.md with the current implementation boundary, enforcement deployment model, live-presence architecture, and hardening references.
- Updated SECURITY.md with the current threat model, enforcement-point requirements, privilege boundaries, and known security work.
- Added a Linux diagnostics regression test.
- Made controlled profile semantics explicit and added policy precedence tests.
- Confirmed DiscoveryService accepts reconciliation settings and LivePresenceService propagates them.
- Added a CI prerequisite probe and verbose firewall integration invocation for the remaining network-namespace failure.
- Added a basic firewall self-lockout guard for the local host and detected gateway, with regression coverage.

This file should be updated whenever a finding is fixed, superseded, or split into smaller engineering tasks.
