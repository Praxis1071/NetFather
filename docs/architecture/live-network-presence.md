# Live network presence

NetFather now has an optional continuous presence layer for Linux desktops.

## Fast path

The application starts `ip monitor neigh` in a small background thread. Linux exposes neighbor-table creation and deletion notifications through rtnetlink; `ip monitor neigh` consumes that kernel notification stream. This avoids continuous packet capture and does not require the GTK application to run as root.

When a relevant neighbor event arrives, NetFather applies an immediate online/offline transition for a known MAC-backed device, then debounces bursts for 750 ms and runs a lightweight hybrid discovery reconciliation. The normal device manager remains the single source of truth.

## Safety path

Neighbor notifications are not sufficient to prove that a device is still reachable forever. A periodic hybrid discovery refresh therefore runs as a safety net. The interval is configurable in Settings and defaults to 30 seconds for the live-presence layer.

## UI behavior

Settings > General exposes:

- enable/disable live presence monitoring
- safety discovery interval

The GTK application remains unprivileged. Deep Nmap inventory remains an explicit scan operation and can request authorization only for that process.

## Why both mechanisms

Linux neighbor notifications provide low-latency state changes, while periodic discovery catches missed notifications, stale neighbor state, and devices that were not previously present in the cache. NetworkManager/libnm remains a future integration point for interface/device lifecycle signals; its `device-added` and `device-removed` signals are about local network interfaces rather than every remote LAN client.
