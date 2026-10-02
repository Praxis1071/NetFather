# Live network presence

NetFather now has an optional continuous presence layer for Linux desktops.

## Fast path

The application starts `ip monitor neigh` in a small background thread. Linux exposes neighbor-table creation and deletion notifications through rtnetlink; `ip monitor neigh` consumes that kernel notification stream. This avoids continuous packet capture and does not require the GTK application to run as root.

Positive neighbor events can immediately update a known MAC-backed device. `Deleted` and `FAILED` events only request reconciliation: removal of a cache entry does not prove the device has left every network path. Events are debounced for 750 ms before a lightweight hybrid discovery reconciliation. The device manager remains the persistence source of truth.

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

The current parser still treats resolved STALE/DELAY/PROBE and permanent entries as positive cache observations. This work does not establish fresh reachability from those states. Evidence aging remains a separate roadmap item. IPv6 address selection/enforcement and topology-scoped expiration also remain open.

The unprivileged integration suite in `tests/integration/test_presence_reconciliation.py` runs real services, resolver, SQLite transactions and audit persistence with controlled OS sources and timers. It does not replace a kernel/netns presence test or GTK runtime verification.
