# Live network presence

NetFather now has an optional continuous presence layer for Linux desktops.

## Fast path

The application starts `ip monitor neigh` in a small background thread. Linux exposes neighbor-table creation and deletion notifications through rtnetlink; `ip monitor neigh` consumes that kernel notification stream. This avoids continuous packet capture and does not require the GTK application to run as root.

REACHABLE neighbor events can immediately update a known MAC-backed device. Cache creation, unconfirmed states, `Deleted` and `FAILED` events only request reconciliation: a cached binding or its removal does not prove reachability across every network path. Events are debounced for 750 ms before a lightweight hybrid discovery reconciliation. The device manager remains the persistence source of truth.

## Safety path

Neighbor notifications are not sufficient to prove that a device is still reachable forever. A periodic hybrid discovery refresh therefore runs as a safety net. The interval is configurable in Settings and defaults to 30 seconds for the live-presence layer.

## UI behavior

Settings > General exposes:

- enable/disable live presence monitoring
- safety discovery interval

The GTK application remains unprivileged. Deep Nmap inventory remains an explicit scan operation and can request authorization only for that process.

## Why both mechanisms

Linux neighbor notifications provide low-latency state changes, while periodic discovery catches missed notifications, stale neighbor state, and devices that were not previously present in the cache. NetworkManager/libnm remains a future integration point for interface/device lifecycle signals; its `device-added` and `device-removed` signals are about local network interfaces rather than every remote LAN client.

## Offline grace and failed observations

- A successful discovery cycle may mark an absent device offline when `last_seen` is at least `offline_after_seconds` old (45 seconds by default, clamped to at least one second).
- A removal hint does not shorten that grace or create an immediate offline audit event.
- Failed or incomplete source cycles preserve absent devices, their last-known IP/last-seen values and runtime identity status. Positive observations from the other successful sources still update devices and DHCP history.
- Missing iproute2, timeouts, nonzero exits, denied ARP and unavailable active subnets produce warnings instead of successful empty inventories. Both passive address-family commands must succeed for a complete passive scan.
- FAILED/INCOMPLETE neighbor records are excluded from positive observations.
- Resolver and persistent state use the same configured missing-device grace. Duplicate polls do not create duplicate departure events; recovery creates an online event once.
- `DiscoverySnapshot.complete` and `warnings` distinguish a partial scan from a successful empty scan; the Discovery workspace displays the warnings.

## Cache evidence and aging

The [iproute2 NUD definitions](https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2/+/refs/heads/main/man/man8/ip-neighbour.8) distinguish REACHABLE from pending validation, suspicious cached entries and static bindings. NetFather therefore applies these rules:

- REACHABLE neighbor entries, active ARP replies and live Nmap results can refresh presence. The parser extracts state independently of flags such as router/managed; an unspecified kernel state becomes NONE.
- STALE, DELAY, PROBE, PERMANENT, NOARP and NONE remain inventory evidence in `DiscoveryReport.hosts` and the list-returning inventory API. They do not refresh last_seen, overwrite the current confirmed IP, auto-register devices or create online identities. Existing API callers may still omit state when supplying a positive observation.
- On a complete scan with no confirmed observation for a known MAC, the device and its runtime identity expire after the configured grace measured from their last confirmed observation. Repeating cache entries or cache-only monitor events does not restart that clock. Offline means the presence grace expired; it is not proof that the physical device disconnected.
- A confirmed observation on any merged address/interface keeps that MAC present. It supplies the selected IP/interface even when a cached alternate path appears first. Active replies can replace cached DHCP addresses. Cache evidence does not demote a confirmed observation later in the same scan.
- A failed source still makes the cycle incomplete and suppresses expiry. Positive observations from other successful sources remain useful.

This is MAC-level presence aggregation using the existing single selected address, not a complete multi-address identity model. IPv6 address selection/enforcement, complete per-path history and topology-scoped expiration remain open. Real kernel notification and GTK runtime verification are also required before closing the Phase I gate.

The unprivileged integration suite in `tests/integration/test_presence_reconciliation.py` runs real services, resolver, SQLite transactions and audit persistence with controlled OS sources and timers. It does not replace a kernel/netns presence test or GTK runtime verification.
