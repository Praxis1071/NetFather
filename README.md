# NetFather

NetFather is a Linux-first, open-source local network management and parental-control application built with GTK4.

Its goal is to discover devices on the local network, identify them, assign them to user profiles, schedule access policies, enforce those policies at real network-traffic level, and provide clear live monitoring.

## Current direction

NetFather 0.5.0 moves the user experience completely to a GTK4 desktop application. The former CLI and TUI interfaces are retired. The reusable core remains responsible for configuration, SQLite persistence, device/profile/rule management, discovery, policy evaluation, monitoring, scheduling and nftables enforcement.

### GTK4 application sections

- Dashboard
- Network Discovery
- Devices
- Network Topology
- Profiles
- Rules
- Monitoring
- Events
- Settings

The first GTK4 shell is now in place. Discovery and device views already connect to the existing Linux backend; the remaining sections will be implemented incrementally on the same core.

## Linux requirements

- Linux
- Python 3.12+
- GTK 4
- GObject Introspection / PyGObject
- iproute2
- nftables (required for traffic enforcement)
- Scapy-compatible packet access for active discovery

On Debian/Ubuntu systems, the GTK runtime development packages used for development can be installed with:

```text
sudo apt install libgirepository1.0-dev gir1.2-gtk-4.0 libcairo2-dev pkg-config
```

Then install Python dependencies with `pip install -r requirements.txt`.

## Architecture

```text
GTK4 GUI
   |
   +-- core configuration / database
   +-- managers: devices / profiles / rules / policy / events
   +-- network: interface / discovery / topology
   +-- monitor / scheduler
   +-- firewall: Linux nftables
```

The GUI is a presentation layer. Network discovery, policy evaluation and firewall enforcement remain outside the GTK widgets so they can evolve independently.

## Development

Run the application from the project checkout with:

```text
python netfather.py
```

Run tests with:

```text
python -m pytest -q
```

NetFather is licensed under the MIT License.
