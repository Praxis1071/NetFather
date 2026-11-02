# Discovery, live-presence and GUI contribution plan

Current Phases I–III implementation and acceptance supersede the historical
next-work list below; see [PHASES-I-III.md](PHASES-I-III.md).

Baseline: `cb0f20083d542cb455c4fbb11b94d5b7f12caf90` (2026-10-01).

## Why this contribution comes first

The active execution queue prioritizes verification and authoritative network
truth before identity/topology, policy, privileged services and enforcement.
Device presence feeds inventory, topology and policy decisions, so a discovery
failure must not appear as a successful observation that every device left.

Upstream has no open issues or PRs at the time of inspection. No AGENTS.md or
CONTRIBUTING file is present. The implementation keeps the existing Linux-only
GTK4 direction and the separation between GUI, service, manager and backend.

## Execution and acceptance

| Step | Change | Acceptance evidence |
| --- | --- | --- |
| 1 | Verify the baseline and preserve the contribution scope | Upstream CI run 36848741182 passed all five jobs, including existing TCP flow and block/recovery namespace tests |
| 2 | Separate a successful empty scan from failed observation sources | Missing iproute2, timeout, OS error, nonzero exit, missing Scapy, denied ARP and invalid targets produce incomplete reports/warnings |
| 3 | Retain successful-source observations without expiring absent devices | Real discovery service, resolver and SQLite tests preserve existing state/history while applying a DHCP address update |
| 4 | Respect departure grace in both runtime and persistence | Deleted/FAILED monitor hints request reconciliation; an absent device expires only after grace on a complete scan |
| 5 | Show degraded discovery and honor manual scan settings | Production GTK callback bodies are tested for partial-scan warning feedback and captured auto-registration/grace settings |
| 6 | Verify and document the contribution | Local Python 3.12 tests, compile checks, version consistency and diff checks; fresh PR CI and graphical QA remain required |

Implementation and regression coverage for steps 2–5 are included in this
contribution. This is a scoped advance in Phase I, not completion of that phase
or permission to skip its stabilization gate.

## Implementation boundaries

- `DiscoveryReport` holds observations, source warnings and a completeness flag.
- `scan_network_report()` is the persistence-facing API. The existing
  `scan_network()` list-returning inventory API remains available.
- Requested sources run independently. A failed passive family makes passive
  discovery incomplete; a successful ARP source can still supply observations.
- On an incomplete report, positive observations remain useful, while absent
  devices and runtime identities retain their previous status.
- Missing iproute2 or denied ARP therefore cannot masquerade as a complete
  empty network. Deep inventory warnings also conservatively suppress expiry.
- FAILED/INCOMPLETE neighbor entries cannot refresh presence as positive evidence.
- Removal hints no longer bypass `offline_after_seconds`. Duplicate departure
  polls produce one persistent event; recovery produces one online event.
- Manager persistence completes before runtime identity reconciliation, so a
  failed persistence operation does not prematurely expire runtime identities.
- GTK controls/configuration are captured before dispatching the worker.
- No firewall, privilege, database schema or version change is made.

## Verification record

Local interpreter: Python 3.12.14. Dependencies match the supported SQLAlchemy
2.0 range. The local environment lacks GTK/PyGObject and namespace tools.

```bash
python -m pytest -q --ignore=tests/test_application_state.py --ignore=tests/test_state.py
python -m compileall -q core gui manager network tests
python scripts/check_version.py --tag v0.5.0
git diff --check
```

Result: **142 passed, 2 skipped**. The two excluded files require GTK imports;
the two skipped tests require real privileged ip/nft namespace support. The
same baseline selection passed 116 tests before this contribution, so this
contribution adds 26 passing test cases.

The callback tests execute the actual production callback bodies with
controlled state/controls. They verify feedback and dispatch contracts, not
graphical rendering. The presence integration tests use real services,
identity resolution, SQLite transactions and audit history with controlled
OS observations, clocks and timers. They do not claim to verify kernel events.

Before merge, run the repository's normal `python -m pytest -q` in a supported
GTK environment and require fresh PR CI across Python 3.12/3.13/3.14, editable
installation and privileged namespace tests. Verify partial-scan warnings and
configured auto-registration/grace in a graphical GTK session.

## Requested GUI contribution

The user requested light/dark appearance, language support, their About credit,
a localized About page and necessary GUI improvements after the first scoped
network contribution. This second implementation slice adds:

- Persistent system/light/dark preferences, applied immediately through GTK.
- System/English/Turkish/Azerbaijani selection, applied at the next launch.
- Complete 214-message catalogs, translated About and contributor profile.
- Dedicated Settings/About/theme modules, manual navigation collapse, two-column
  metrics, stacked creation forms and clearer desired-policy labels.
- Label-independent pause state, corrected switch persistence and save-failure
  rollback. GTK-independent state imports allow the normal complete test suite
  to run in this environment.
- Wheel and PyInstaller translation-resource inclusion.

Current verification: `python -m pytest -q` reports **189 passed, 2 skipped**.
No test files are excluded. The skipped tests require privileged ip/nft network
namespaces. Compilation, version consistency and diff checks pass. The wheel
build succeeds and all three languages load from the wheel in an isolated
process. PyInstaller build and graphical GTK rendering were not run here.

See [GUI preferences and remaining graphical QA](GUI-PREFERENCES.md). Roadmap
appearance, localization and narrow-window work stays partially complete until
its graphical/runtime checks pass; the Phase I stabilization gate is unchanged.

## Next roadmap work

1. Verify cache-evidence aging against real kernel notifications; extend the
   MAC-level confirmed-path selection into full multi-address/interface history.
2. Add actual kernel neighbor-notification integration tests and discovery
   cancellation tests that preserve identity and persistence.
3. Finish IPv6 observation/address selection, identity conflict and topology
   safeguards before exposing complete remote enforcement.
4. Establish the canonical runtime event bus and narrow D-Bus/polkit service.
5. Validate IPv4/IPv6 enforcement, failure recovery and kernel reconciliation
   before completing monitoring, bandwidth control and release gates.

The root ROADMAP remains the authority for ordering. This plan records only
the contribution slice and its acceptance boundaries.

## Cache-evidence aging follow-up — 2026-11-01

Baseline: `e22a0125e04bb8389ae7751125fa891c9bf03165`, verified by
[main CI run 40221763261](https://github.com/Praxis1071/NetFather/actions/runs/40221763261).
There were no open upstream issues or PRs when this slice began. It follows
active execution queue item 7 and leaves the Phase I stabilization gate open.

Cache-only NUD observations stay in discovery reports but cannot renew
last_seen, replace a confirmed IP or create online devices. Only REACHABLE
neighbor events take the direct presence-update path. Complete reconciliation
ages cached devices using the existing grace; incomplete reports preserve their
prior state. Confirmed alternate paths win over cached ones in either ordering,
and active replies replace cached DHCP targets.

Added 51 regression cases covering parser flags and state, repeated cache
polls/events, grace boundaries, no duplicate departure/recovery events, partial
source failure, unknown cached MACs, legacy sync and confirmed alternate paths.
Tests use actual discovery, identity, manager and SQLite code with controlled
OS sources/timers; they do not verify real kernel notifications or GTK rendering.

Local environment: Windows / Python 3.13.5, SQLAlchemy 2.0.45. With
`PYTHONUTF8=1`, the complete suite reports **245 passed, 2 skipped, 5 failed**.
The same five failures existed before this change: Linux permission/geteuid
expectations and Windows paths interpolated unescaped into TOML test fixtures.
The first baseline run without UTF-8 mode had one additional catalog decoding
failure. The skipped cases require privileged Linux network namespaces.
Compilation, version consistency and `git diff --check` pass.

Fresh PR CI must verify the supported Python 3.12/3.13/3.14 matrix, editable
installation and privileged firewall namespace tests. Linux-only scope and all
remaining real-kernel, GTK, IPv6 target-selection and topology gates are retained.
