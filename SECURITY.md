# Security Policy

NetFather is a **Linux-only local-network management application**. Use it only on networks and devices you are authorized to administer.

## Security posture

NetFather is an actively developed, security-sensitive network application. The presence of discovery, policy, and nftables components does not mean that every installation is a production-ready parental-control gateway.

The project currently separates:

1. **Discovery** — finding and enriching local devices.
2. **Identity** — determining which observations belong to the same device.
3. **Policy** — deciding whether a managed device should be allowed or blocked.
4. **Enforcement** — applying that decision to actual traffic at a valid Linux traffic path.
5. **Monitoring and events** — recording what the system observed and changed.

A failure in any one of these layers can make a policy ineffective, so end-to-end integration tests are treated as security requirements rather than optional polish.

## Enforcement-point security

A NetFather desktop host is not automatically an enforcement point for other LAN devices.

For another device's internet access to be controlled, the managed traffic must actually traverse the Linux system where NetFather installs its nftables policy. Supported deployment work is centered on Linux gateway/router or other valid inline/bridge enforcement topologies.

The project must not imply that discovering a device grants control over its traffic.

The default firewall configuration is disabled. Verify the traffic path and recovery procedure before enabling enforcement.

## Firewall isolation

NetFather owns the dedicated Linux nftables table named `netfather`. It must not flush or replace unrelated host firewall tables.

The current backend still has hardening work outstanding:

- replace destructive table recreation with atomic named-set element updates;
- preserve counters and NetFather state across policy changes;
- handle policy changes for existing connections through an explicit conntrack strategy;
- protect the NetFather management path from self-lockout;
- validate the actual enforcement point before applying remote-device restrictions;
- move privileged firewall operations behind a narrowly scoped D-Bus service with polkit authorization.

Until these are complete, the firewall layer should be considered an active hardening target.

## Privileged operations

NetFather should **not** be run as a root GTK desktop application.

- Passive Linux neighbor discovery can run without root.
- Scapy ARP discovery may require networking privileges depending on the environment.
- Deep Nmap operations such as raw-packet SYN/UDP/OS probing may require elevated authorization.
- The current deep-scan path can request per-scan authorization through `pkexec`.
- Future firewall/service operations are intended to use a narrowly scoped privileged D-Bus service with polkit.

Privilege should be granted per operation, not to the entire GUI.

## Network scanning safety

Deep inventory is restricted to private or link-local IPv4 targets and rejects networks broader than `/16`.

Deep inventory is not a vulnerability scanner. It deliberately does not enable Nmap NSE/default scripts.

Service/version and OS probing still generate network traffic and may interact poorly with fragile devices. Only run deep inventory on networks you administer.

The scanning architecture is being hardened toward:

- host-discovery-first behavior;
- bounded target lists;
- optional expensive UDP/version/OS stages;
- explicit warnings when capabilities are unavailable;
- no default vulnerability-script execution.

## Device identity and privacy

Device identity must not rely permanently on a current IPv4 address because DHCP can change addresses.

Network metadata should be treated as sensitive, including:

- MAC addresses;
- IP addresses;
- hostnames;
- vendor/device information;
- identity and discovery history;
- policy history;
- firewall and event logs.

NetFather is designed to keep MAC/OUI vendor resolution local and should not send MAC addresses to remote lookup services.

Do not publish real network inventories, logs, database files, or screenshots containing network metadata.

The local configuration and data directories use restrictive permissions where the underlying filesystem supports them. This is defense-in-depth, not a substitute for host security.

## Live presence

The Linux neighbor-monitoring layer is intended as a fast signal, not as the sole source of truth.

Current behavior:

- `ip monitor neigh` provides low-latency presence notifications;
- events are debounced;
- discovery reconciliation updates persistent device state;
- periodic discovery remains the safety mechanism.

The target architecture will additionally provide direct state transitions and a central runtime event bus, while retaining periodic reconciliation to recover from missed notifications.

## Known security work in progress

The authoritative engineering checklist is [docs/TECHNICAL-DEBT.md](docs/TECHNICAL-DEBT.md).

Highest-priority security/correctness work currently includes:

1. nftables network-namespace integration reliability;
2. enforcement-point validation and deployment model;
3. self-lockout protection;
4. durable identity/history for enforcement;
5. atomic nftables named-set updates;
6. conntrack handling for policy transitions;
7. privileged D-Bus/polkit separation;
8. end-to-end discovery-to-enforcement tests;
9. live event propagation and audit consistency;
10. host-discovery-first deep scanning.

Until the relevant hardening items are complete, NetFather should be treated as an actively developed security-sensitive application rather than a finished network-control appliance.

## Reporting a vulnerability

Please do not publish sensitive exploit details in a public issue.

Report security vulnerabilities privately through GitHub's private security reporting mechanism when available. Include:

- affected version/commit;
- Linux distribution and kernel version;
- minimal reproduction steps;
- relevant logs with real MAC/IP values anonymized;
- whether firewall enforcement was enabled;
- whether elevated privileges were used.

Do not include passwords, access tokens, private keys, or other credentials in reports.

If private reporting is unavailable, open a minimal public issue that only requests a private contact path and does not disclose exploit details.
