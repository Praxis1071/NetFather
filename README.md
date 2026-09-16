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

The current implementation includes:

- GTK4 application shell with animated workspace navigation;
- shared application state and GTK-safe background task handling;
- a dashboard control center with live network, device, policy, and traffic summaries;
- Linux network interface information;
- passive, active, and hybrid local-network discovery;
- Scapy-based ARP discovery;
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

For CachyOS / Arch Linux, install the main system dependencies with:

```bash
sudo pacman -S --needed python gtk4 python-gobject iproute2 nftables
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

Some network discovery and traffic-enforcement operations require appropriate Linux privileges.

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
   |                |                |
   +----------------+----------------+
                    |
                    v
             Network Core
       Identity / Presence / State
                    |
                    v
             Enforcement
          nftables / tc / service
```

The long-term GUI will use GTK4/Libadwaita patterns where they improve adaptive navigation, accessibility, and desktop integration. The current GTK4 stack already uses non-blocking background work and lightweight page transitions.

## Development focus

The roadmap is intentionally incremental:

1. application core and stable device identity;
2. modular and richer network discovery;
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

MIT
