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

NetFather 0.5.0 is in active hardening and GTK4 application development.

The project is **not yet a finished traffic-enforcement appliance**. Discovery, identity, profiles, rules, policy evaluation, live-presence foundations, monitoring, and an nftables backend exist, but the complete production path from persistent device identity to safe real-network enforcement is still being integration-tested.

The current hardening checklist is maintained in [docs/TECHNICAL-DEBT.md](docs/TECHNICAL-DEBT.md). Work is performed in priority order, with firewall correctness, enforcement topology, policy semantics, identity persistence, live events, and privileged-service separation treated as security-sensitive areas.

Current implementation includes:

- GTK4 application shell with animated workspace navigation;
- shared application state and GTK-safe background task handling;
- dashboard control center with network, device, policy, and traffic summaries;
- Linux network interface information;
- passive, active, hybrid, and optional deep local-network discovery;
- Scapy-based ARP discovery;
- Linux `ip neigh` neighbor-state discovery;
- optional Nmap TCP/UDP service inventory and service-version detection;
- optional Nmap OS fingerprinting with bounded local-network targets;
- optional per-scan authorization through `pkexec`;
- hostname, vendor, device-type, and OS-hint enrichment;
- stable in-memory identity resolution independent of the current IP;
- automatic discovery reconciliation through the device manager;
- partial-scan warnings and preservation of last-known presence when a requested discovery source fails;
- functional GTK4 Network Discovery and Devices workspaces;
- live gateway-centered Network Topology workspace;
- Profiles and Rules workspaces connected to backend managers;
- shared Policy Service for effective policy snapshots;
- live GTK4 Monitoring workspace backed by Linux interface counters;
- GTK4 Events workspace backed by persistent audit/event history;
- SQLite persistence through SQLAlchemy;
- Linux nftables firewall backend;
- policy, scheduler, firewall, monitoring, and event foundations that are being connected incrementally toward real traffic enforcement.

Real packet-level enforcement is deliberately **not** presented as complete until the enforcement path, deployment topology, identity handling, recovery behavior, and integration tests are all validated.

## Network enforcement model

Discovery and enforcement are separate concepts.

A normal Linux desktop running NetFather can discover devices on its local network, but that does **not** automatically give it control over those devices' internet traffic. To enforce another device's traffic, NetFather must run at a valid traffic enforcement point, for example:

- the Linux gateway/router for the managed LAN;
- a Linux bridge/router through which the managed traffic actually passes;
- another explicitly supported inline enforcement topology.

The current nftables backend installs rules in NetFather's dedicated `inet netfather` table. It does not flush unrelated firewall tables. The project is moving toward persistent named sets and event-driven updates rather than rebuilding the whole table for every policy change.

The default configuration keeps enforcement disabled. Do not enable enforcement on a production network until the deployment topology and recovery behavior have been verified. Enforcement is also runtime-gated: set `firewall.enforcement_topology = "gateway"` for a Linux router with IPv4 forwarding enabled, or `"inline"` for an explicitly verified inline path. `unverified`/ `host` configurations cannot apply remote-device enforcement.

## Discovery modes

The Discovery workspace is layered:

- **Passive** — read the Linux neighbor table without active probing.
- **Active ARP** — use Scapy Ethernet/ARP discovery for local IPv4 hosts.
- **Hybrid** — combine passive neighbor state and active ARP discovery, then reconcile identities.
- **Deep inventory** — combine local discovery with optional Nmap service/version, UDP, and OS probing.

Deep inventory is restricted to private or link-local IPv4 networks and currently refuses networks broader than `/16`. Expensive deep probes are intended to be applied only to discovered live hosts as the scanning pipeline matures.

Deep inventory does not enable Nmap NSE/default scripts. The feature is for network inventory, not vulnerability scanning.

Nmap is optional for the base application. If it is not installed, normal discovery modes continue to work. For Arch/CachyOS:

```bash
sudo pacman -S --needed nmap
```

## Live network presence

Linux neighbor notifications through `ip monitor neigh` provide a fast presence signal. Positive events can update known devices immediately; removal/failure hints trigger debounced reconciliation and respect the configured offline grace. Incomplete discovery cycles preserve absent devices instead of interpreting source failures as an empty network. STALE cache evidence aging remains open; see [live presence semantics](docs/architecture/live-network-presence.md).

The longer-term design is:

```text
kernel neighbor event
        |
        v
direct presence state transition
        |
        +----> runtime event bus
        |
        +----> persistent device/event state
        |
        v
periodic discovery safety reconciliation
```

This avoids treating a single transient neighbor-cache event as authoritative.

## GTK4 GUI direction

The target UI is:

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

The project is developed and tested primarily on **CachyOS**, an Arch Linux-based distribution. Debian/Ubuntu-family systems, Fedora, and openSUSE Tumbleweed should also be usable when their packages meet the requirements below, but they are best-effort platforms and are not tested as extensively as CachyOS/Arch.

Requirements include **Python 3.12 or newer**. Older releases that ship Python 3.11 or earlier are not supported unless you provide a separate Python 3.12+ interpreter. Windows and macOS are not project targets.

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

### System packages by distribution

Install the native GTK/PyGObject libraries and networking tools with your distribution's package manager. Package names can vary slightly by release.

**CachyOS / Arch Linux**

```bash
sudo pacman -S --needed python python-pip python-gobject gtk4 iproute2 nftables nmap polkit
```

**Debian 13+ / Ubuntu 24.04+ / Linux Mint based on Ubuntu 24.04+**

These releases provide Python 3.12 or newer by default. Debian/Ubuntu package names:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-gi gir1.2-gtk-4.0 \
  iproute2 nftables nmap polkit python3-scapy python3-sqlalchemy python3-psutil
```

**Fedora (a release providing Python 3.12 or newer)**

```bash
sudo dnf install python3 python3-pip python3-gobject gtk4 \
  iproute nftables nmap polkit python3-scapy python3-sqlalchemy python3-psutil
```

**openSUSE Tumbleweed**

```bash
sudo zypper refresh
sudo zypper install python3 python3-pip python3-gobject gtk4 \
  iproute2 nftables nmap polkit python3-scapy python3-SQLAlchemy python3-psutil
```

If a package is not found, search for the equivalent package in your release. NetFather requires Python 3.12+, GTK 4 and working PyGObject/GObject Introspection bindings. Nmap is optional; without it, basic discovery can still be used. Other distributions may work if they provide these dependencies, but installation and runtime behavior have not been verified on every distribution.

### Install NetFather in a Python virtual environment (all distributions)

NetFather should be run from a Python virtual environment. The environment should use **system site packages** because GTK4/PyGObject is provided by the distribution and depends on native GObject libraries; installing PyGObject from PyPI inside a normal isolated venv can fail or create an unnecessary native-build problem.

From the repository root, using Fish:

```fish
python -m venv --system-site-packages .venv
source .venv/bin/activate.fish
python -m pip install --upgrade pip
python -m pip install -e .
```

The same setup with Bash/Zsh is:

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

After installation, the project can be started from the activated environment with:

```bash
python -m gui.app
```

or:

```bash
netfather
```

To use NetFather again later:

```fish
source .venv/bin/activate.fish
netfather
```

To leave the environment:

```fish
deactivate
```

For development and tests, install the development dependencies after activating the venv:

```fish
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

If the venv was created without `--system-site-packages`, recreate it with that option rather than trying to force-install the system GTK/PyGObject stack into the venv.

Some discovery and enforcement operations require appropriate Linux privileges. Deep discovery can request authorization only for the Nmap process rather than running the whole GUI as root. Do not run the entire GTK application as root.
## Testing

Run the normal suite with:

```bash
python -m pytest -q
```

The CI pipeline also contains a Linux nftables/network-namespace integration test. A green Python unit-test matrix is not considered sufficient evidence of firewall correctness.

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

### Appearance and language

Open **Settings → General → Appearance and language** to choose **Follow system**, **Light**, or **Dark**. Theme changes apply immediately and are saved. The system option follows GNOME's color-scheme preference when available and otherwise uses GTK's startup preference.

Choose **System language**, **English**, **Türkçe**, or **Azərbaycanca**. Language changes are saved and apply after restarting NetFather. Navigation, controls, status messages and About use the selected language. Unsupported system languages fall back to English; backend diagnostics and historical event descriptions retain their original content.

The About page retains the original developer, Praxis1071, and includes contributor Cavanşir Qurbanzadə (YoungLion) with [his GitHub profile](https://github.com/Cavanshirpro). The header button can hide navigation; Dashboard/Monitoring cards use two columns, and Profiles/Rules forms stack vertically for smaller windows.

See [GUI preferences and translation maintenance](docs/GUI-PREFERENCES.md) for configuration, adding translations and remaining graphical verification.

See:

- [docs/architecture/network-discovery-stack.md](docs/architecture/network-discovery-stack.md)
- [docs/architecture/live-network-presence.md](docs/architecture/live-network-presence.md)
- [docs/TECHNICAL-DEBT.md](docs/TECHNICAL-DEBT.md)
- [SECURITY.md](SECURITY.md)

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
