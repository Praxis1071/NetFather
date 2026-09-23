# Security Policy

NetFather is a **Linux-only local-network management application**. Use it only on networks and devices you are authorized to administer.

## Security scope

NetFather can discover local-network devices and, when explicitly enabled and correctly deployed, manage network access policies. Discovery is inventory-oriented; the normal deep-inventory path does not enable Nmap NSE/default scripts or vulnerability-scanning workflows.

The project currently treats real packet-level enforcement as a security-sensitive feature under active hardening. The presence of an nftables backend does not mean that every deployment topology is already protected by NetFather. The enforcement point must actually be on the traffic path that NetFather is intended to control.

## Privileged operations

NetFather should **not** be run as a root GTK desktop application.

- Passive Linux neighbor discovery can run without root.
- Scapy ARP discovery may require the privileges available to the local Linux networking environment.
- Deep Nmap features such as raw-packet SYN/OS/UDP operations may require elevated authorization.
- The current deep-scan implementation can request per-scan authorization through pkexec; this is intentionally narrower than running the whole GUI with elevated privileges.
- Future privileged operations are intended to move behind a narrowly scoped D-Bus/system service with polkit authorization.

Do not grant more privilege than the operation requires.

## Network scan safety

Deep inventory is restricted to private or link-local IPv4 targets and rejects networks broader than /16. It is intended for local inventory, not internet-wide scanning.

The normal deep inventory path does not enable Nmap NSE/default scripts. Service/version and OS probing can still generate traffic and may interact poorly with fragile devices, so use deep scanning only on networks you administer.

## Firewall isolation

NetFather owns the dedicated Linux nftables table named netfather. It must not flush unrelated host firewall tables.

Current enforcement is intentionally limited while the project is being hardened:

- policy targets are local private/link-local IPv4 addresses;
- the default configuration keeps enforcement disabled;
- nftables changes must be explicitly applied;
- the project is moving toward atomic named-set updates rather than destructive table replacement;
- self-lockout protection and privileged-service separation are required before the enforcement subsystem is considered production-ready.

NetFather should not be assumed to control another device's traffic merely because its GUI can discover that device. For another device's internet access to be enforced, NetFather must be deployed at an appropriate network enforcement point, such as the relevant Linux gateway/router or another valid traffic path.

## Data and privacy

NetFather is designed to keep MAC/OUI vendor resolution local. The application should not send MAC addresses to remote vendor-lookup services.

Treat the following as sensitive network metadata:

- MAC addresses;
- IP addresses;
- hostnames;
- device/vendor information;
- discovery history;
- policy and event history.

Do not publish real network inventories, logs, database files, or screenshots containing this information.

The local configuration and data directories are created with restrictive permissions where the underlying filesystem supports them. This is defense-in-depth, not a substitute for correct host security.

## Known security work in progress

The following items are explicitly tracked in docs/TECHNICAL-DEBT.md:

1. privileged-service/D-Bus separation;
2. enforcement-point validation and deployment model;
3. self-lockout protection;
4. persistent identity history;
5. atomic nftables set updates;
6. conntrack handling when policies change;
7. end-to-end enforcement tests;
8. live event propagation and audit consistency;
9. stronger deep-scan bounds and host-discovery-first behavior.

Until these are complete, NetFather should be treated as an actively developed security-sensitive application rather than a finished parental-control appliance.

## Reporting a vulnerability

Please do not publish sensitive exploit details in a public issue.

Report security vulnerabilities privately to the repository owner through GitHub's private security reporting mechanism when available. Include:

- affected version/commit;
- Linux distribution and kernel version;
- minimal reproduction steps;
- relevant logs with real MAC/IP values anonymized;
- whether firewall enforcement was enabled;
- whether elevated privileges were used.

Do not include passwords, access tokens, private keys, or other credentials in reports.

If private reporting is unavailable, open a minimal public issue that only requests a private contact path and does not disclose exploit details.
