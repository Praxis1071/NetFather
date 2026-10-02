# NetFather Network Discovery Stack

NetFather uses a layered discovery model instead of treating one probe as authoritative.

## Layers

1. **Linux neighbor state** — `ip neigh` provides the kernel's current IPv4 neighbor knowledge and link-layer addresses.
2. **Scapy ARP discovery** — active layer-2 discovery finds hosts that are not already present in the neighbor table.
3. **Hostname and vendor enrichment** — reverse DNS and MAC-prefix lookup add context without changing the stable identity key.
4. **Deep Nmap inventory** — an explicit `Deep inventory` mode can enumerate TCP/UDP services, service versions and OS fingerprints.
5. **Identity resolution** — observations are reconciled around MAC/device identity rather than treating an IP address as a permanent device identity.

## Deep inventory

The deep mode is intentionally optional because service/version and OS probes are more expensive than host discovery. Nmap is used when installed. The scan is bounded to private or link-local IPv4 networks and currently rejects networks broader than `/16`.

The GTK application can request elevation for only the Nmap process through `pkexec`. NetFather itself remains an unprivileged GTK process. Without elevation, Nmap uses a TCP connect scan and skips raw-packet-only OS/UDP capabilities when unavailable.

Deep inventory exposes:

- discovered MAC address and vendor
- hostname
- device type
- open TCP ports
- open UDP ports when privileged
- service/application names and versions
- OS fingerprint and confidence when privileged
- latency when supplied by Nmap

Default deep scanning deliberately does **not** enable Nmap NSE/default scripts. Script execution is a separate future feature because Nmap documents default script scanning as intrusive and warns that service/version/OS probing can affect fragile services.

## Why multiple layers?

No single discovery technique sees every host. Local ARP is particularly useful on Ethernet networks, while TCP/UDP probes reveal hosts and services that do not answer ICMP. Nmap's OS detection combines many TCP/IP fingerprint tests, while service detection interrogates discovered ports. The result is stronger when these observations are merged rather than replacing one another.

## Future layers

Planned additions include:

- NetworkManager D-Bus presence signals for immediate local interface/connection changes
- IPv6 neighbor discovery
- DHCP lease correlation where available
- mDNS/LLMNR/NetBIOS discovery as opt-in inventory sources
- passive packet observation for presence changes
- persistent service/port inventory history
- confidence scoring that combines independent observations
- privileged D-Bus service for narrow network operations rather than GUI-wide root execution
