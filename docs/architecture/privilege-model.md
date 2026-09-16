# NetFather Linux privilege model

NetFather is designed to run its GTK4 interface as the normal desktop user. It must not require the whole GUI to run as root.

## Why

GTK widgets belong to the GTK main thread, and the desktop application should not turn the entire UI process into a privileged process. Privileged operations are isolated from the presentation layer.

## Capability tiers

### Standard user

The application can use unprivileged Linux state where available, including cached neighbor information and NetworkManager's D-Bus API. NetworkManager exposes device and active-connection signals that are useful for live state changes.

### Elevated discovery

Some active probes and low-level packet operations can benefit from additional Linux capabilities. NetFather should expose this as an explicit capability, not silently invoke `sudo` or ask for a password during an unrelated scan.

### Privileged enforcement

nftables changes are privileged operations. The long-term architecture is a small root-owned system service exposed over D-Bus and authorized with polkit. The GTK process requests narrowly scoped operations from that service.

The service should accept structured operations rather than arbitrary shell commands. It must validate IP addresses, interfaces, table/set names, and policy transitions before applying them.

## Authentication

`pkexec` exists as a compatibility mechanism for explicitly authorized administrative commands, but it should not be used to relaunch the entire GTK application as root. A desktop session normally provides a polkit authentication agent, and polkit is designed for an unprivileged subject communicating with a privileged mechanism over IPC.

## Enforcement design

Use nftables named sets for dynamic blocked-address membership and named counters for traffic accounting. Named sets can be updated without rebuilding the complete ruleset, while counters provide packet and byte measurements. This keeps policy changes incremental and gives the monitoring UI real kernel-backed traffic data.

Future bandwidth controls should use `tc` classification/shaping rather than trying to emulate bandwidth control in Python packet loops.

## UI requirements

Settings should show:

- current privilege state;
- whether `pkexec` is available;
- whether `nft` and `ip` are available;
- whether NetworkManager is available;
- which features require elevation.

The UI should never imply that a privileged capability is active when it is only available. A capability is active only when the backend successfully confirms it.

## Sources

- GTK4 threading: https://docs.gtk.org/gtk4/section-threading.html
- NetworkManager `NMClient` signals: https://www.networkmanager.dev/docs/libnm/latest/NMClient.html
- polkit authorization model: https://polkit.pages.freedesktop.org/polkit/polkit.8.html
- nftables named sets: https://wiki.nftables.org/wiki-nftables/index.php/Sets
- nftables counters: https://wiki.nftables.org/wiki-nftables/index.php/Counters
