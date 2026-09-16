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

- GTK4 application shell and navigation;
- shared application state and background task handling;
- Linux network interface information;
- passive, active, and hybrid local-network discovery;
- Scapy-based ARP discovery;
- hostname, vendor, device-type, and OS-hint enrichment;
- stable device identity resolution independent of the current IP;
- automatic discovery reconciliation through the device manager;
- a functional GTK4 Network Discovery workspace;
- a functional GTK4 Devices workspace with device details, editing, refresh, and deletion;
- SQLite persistence through SQLAlchemy;
- Linux nftables firewall backend;
- profile, rule, policy, monitoring, scheduler, and event foundations that are being connected to the GUI incrementally.

The Dashboard, Discovery, and Devices pages are connected to the backend. Network Topology, Profiles, Rules, Monitoring, Events, and Settings are being implemented incrementally.

## GTK4 GUI direction

The application UI is intentionally being built around GTK4 with a clean, user-friendly desktop experience.

The target is:

- clear and easy to understand;
- option-rich without becoming confusing;
- polished and visually consistent;
- responsive during scans and other long-running operations;
- lightly animated where animation improves feedback;
- free of emoji-based device or status indicators.

The GUI remains a presentation layer. Discovery, device identity, policy evaluation, persistence, and network enforcement stay in the reusable backend instead of being duplicated inside GTK widgets.

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
GTK4 / Libadwaita GUI
          |
          v
   Application State
          |
   +------+------+----------------+
   |             |                |
Devices      Discovery         Policies
   |             |                |
   +-------------+----------------+
                 |
            Network Core
                 |
       +---------+---------+
       |                   |
   Identity            Presence
       |                   |
       +---------+---------+
                 |
            Enforcement
                 |
              nftables
```

The long-term architecture separates the GTK4 presentation layer from the network and policy core. Background operations must not block the GTK main thread.

## Development focus

Current development is intentionally **GUI-first**. New user-facing functionality is implemented in GTK4 and connected to the existing backend services.

The immediate progression is:

1. complete the GTK4 application core;
2. finish device management and identity presentation;
3. build live Network Topology;
4. connect Profiles and Rules;
5. connect Monitoring and Events;
6. integrate real nftables policy enforcement into the GUI workflow;
7. add traffic shaping and deeper live network telemetry;
8. harden the Linux service, security, recovery, testing, packaging, and release workflow.

CLI and TUI interfaces are retired and are **not active development targets**.

## License

NetFather is licensed under the MIT License.
