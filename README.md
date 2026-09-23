# NetFather

NetFather is an open-source Linux network management and parental-control application focused on real local-network device discovery, identity, policy management, and traffic enforcement.

The project is being developed as a **GTK4 desktop application**. The GUI is the only active user interface target.

## Project goal

NetFather is designed to:

- discover devices on the user's local network;
- identify devices reliably even when their IP address changes;
- let users name and manage discovered devices;
- assign devices to profiles;
- define scheduled access policies;
- enforce restrictions at real network-traffic level on Linux;
- provide live network state, topology, monitoring, and event history.

## Current status

NetFather 0.5.0 is in active GTK4 application development.

The project is intentionally **not yet a finished traffic-enforcement product**. Device discovery, identity, profiles, rules, policy evaluation, live presence foundations, monitoring, and an nftables backend exist, but the complete production path from persistent device identity to safe real-network enforcement is still being hardened and integration-tested.

Current engineering priorities are tracked in [docs/TECHNICAL-DEBT.md](docs/TECHNICAL-DEBT.md). The highest-priority work is CI/enforcement reliability, persistent identity, live event propagation, safe nftables updates, privileged-service separation, and end-to-end integration testing.

The current implementation includes:

- GTK4 application shell with animated workspace navigation;
- shared application state and GTK-safe background task handling;
- a dashboard control center with live network, device, policy, and traffic summaries;
- Linux network interface information;
- passive, active, hybrid, and optional deep local-network discovery;
- Scapy-based ARP discovery;
- Linux `ip neigh` neighbor-state discovery;
- optional Nmap TCP/UDP service inventory and service-version detection;
- optional Nmap OS fingerprinting with a bounded local-network scan;
- optional per-scan authorization through `pkexec` so the whole GTK application does not run as root;
- hostname, vendor, device-type, and OS-hint enrichment;
- stable device identity resolution independent of the current IP;
- automatic discovery reconciliation through the device manager;
- functional GTK4 Network Discovery and Devices workspaces;
- live gateway-centered Network Topology workspace;
- Profiles and Rules workspaces connected to the existing backend managers;
- a shared application Policy Service for effective policy snapshots;
- live GTK4 Monitoring workspace backed by Linux interface counters;
- GTK4 Events workspace backed by the persistent audit/event history;
- SQLite persistence through SQLAlchemy;
- Linux nftables firewall backend;
- policy, scheduler, firewall, monitoring, and event foundations that are being connected incrementally toward real traffic enforcement.

Real packet-level enforcement is deliberately not presented as complete until it is fully wired, guarded, and integration-tested.

## Discovery modes

The Discovery workspace is intentionally layered:

- **Passive** — read the Linux neighbor table without actively probing the network.
- **Active ARP** — use Scapy Ethernet/ARP discovery to find local IPv4 hosts that are not already known by the kernel.
- **Hybrid** — combine passive neighbor state and active ARP discovery, then enrich and reconcile identities.
- **Deep inventory** — combine the local discovery layers with Nmap service/version discovery and optional TCP/UDP/OS fingerprinting. The deep mode is restricted to private or link-local IPv4 networks and currently refuses networks broader than `/16`.

Deep inventory does not enable Nmap NSE/default scripts. This keeps the feature focused on network inventory rather than vulnerability scanning and avoids turning the normal discovery workflow into an intrusive script runner.

Nmap is optional for the base application. If it is not installed, the normal discovery modes continue to work. For Arch/CachyOS, install it with:

```bash
sudo pacman -S --needed nmap
```

## GTK4 GUI direction

The application UI is being built as a clean, user-friendly desktop control center.

The target is:

- clear and easy to understand;
- option-rich without becoming confusing;
- polished and visually consistent;
- responsive during scans and other long-running operations;
- lightly animated where animation improves feedback;
- adaptive to different window sizes as the UI matures;
- free of emoji-based device or status indicators.

The GUI remains a presentation layer. Discovery, device identity, policy evaluation, persistence, and network enforcement stay in reusable backend services instead of being duplicated inside GTK widgets.

## Supported platform

**Linux only.**

The project is developed and tested primarily on **CachyOS**, an Arch Linux-based distribution. Other Linux distributions may work when the required system packages are available, but Arch-family/CachyOS is the primary development environment.

Windows and macOS are not project targets.

## Requirements

- Linux
- Python 3.12+
- GTK 4
- PyGObject / GObject Introspection
- iproute2
- nftables
- Scapy
- SQLAlchemy
- psutil
- optional Nmap for deep inventory
- optional polkit/pkexec for per-scan elevation

For CachyOS / Arch Linux, install the main system dependencies with:

```bash
sudo pacman -S --needed python gtk4 python-gobject iproute2 nftables nmap polkit
```

Then install the Python project in an isolated environment according to your preferred Python workflow. The project dependencies are declared in `pyproject.toml`.

## Running

From the project directory:

```bash
python -m gui.app
```

If the project is installed as a package, the `netfather` entry point also launches the GTK4 application:

```bash
netfather
```

Some network discovery and traffic-enforcement operations require appropriate Linux privileges. Deep discovery can request authorization only for the Nmap process rather than running the whole GUI as root.

## Testing

Run the test suite with:

```bash
python -m pytest -q
```

## Architecture

```text
GTK4 GUI
   |
   v
Application State + Background Tasks
   |
   +----------------+----------------+
   |                |                |
Devices          Discovery        Policies
                    |
          +---------+---------+
          |         |         |
       ip neigh   Scapy     Nmap
          |         |         |
          +---------+---------+
                    |
                    v
             Identity / Presence
                    |
                    v
             Enforcement
          nftables / tc / service
```

The long-term GUI will use GTK4/Libadwaita patterns where they improve adaptive navigation, accessibility, and desktop integration. The current GTK4 stack already uses non-blocking background work and lightweight page transitions.

See `docs/architecture/network-discovery-stack.md` for the discovery design and its future extension points.

## Development focus

The roadmap is intentionally incremental:

1. application core and stable device identity;
2. layered network discovery with strong local inventory;
3. live network presence and topology;
4. polished GTK4/Libadwaita GUI workflows;
5. reusable device profiles and scheduled rules;
6. safe real nftables enforcement;
7. traffic monitoring and accounting;
8. bandwidth control with Linux `tc`;
9. privileged-service separation and D-Bus integration;
10. security, recovery, integration testing, and packaging.

The CLI and TUI are retired development targets and should not be reintroduced unless the project direction is explicitly changed.

## License

GNU General Public License v3 or later (GPL-3.0-or-later). See [LICENSE](LICENSE).
