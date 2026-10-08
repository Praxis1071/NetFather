# NetFather Roadmap

NetFather is a Linux-only GTK4 network management and parental-control application. This document is the project's product roadmap and execution order.

**Roadmap baseline:** 2026-10-01

**Current development line:** 0.5.x hardening and GTK4 product completion

---

## 1. Final product goal

NetFather should provide one coherent lifecycle:

**discover devices → identify them reliably → observe live presence → organize devices → assign profiles → define rules → schedule policies → validate the enforcement path → enforce real traffic → monitor results → record events → recover safely**

The important architectural rule is that the GUI is not the network engine. GTK4 presents state and actions; discovery, identity, policy evaluation, persistence, scheduling, enforcement, monitoring, and recovery remain reusable backend services.

NetFather is not considered production-ready merely because a feature exists in the UI. Security-sensitive functionality is complete only when its implementation, tests, integration behavior, failure path, documentation, and CI verification are complete.

---

## 1.1 Research-validated architecture constraints

The final goal is technically achievable on Linux, but the roadmap must respect the boundaries of the underlying Linux networking stack.

- NetworkManager exposes network state and control through D-Bus/libnm, so NetFather should consume NetworkManager state where available instead of treating shell commands as the only source of truth. urlNetworkManager developer documentationturn0search9
- nftables supports stateful IPv4/IPv6 filtering, sets, counters, and transactional ruleset updates; NetFather should therefore keep enforcement isolated in its own nftables objects and reconcile desired state with actual kernel state. urlnftables documentationturn0search12 urlLinux nftables netlink specificationturn2search12
- Traffic shaping belongs to Linux traffic control (tc), whose qdisc/class/filter model is separate from packet filtering. Bandwidth control therefore remains an advanced enforcement subsystem rather than being mixed into the firewall engine. urlLinux tc documentationturn2search0
- Privileged operations should be exposed through a narrow system service and authorization boundary. polkit is explicitly designed for privileged mechanisms serving unprivileged clients and supports per-action authorization. urlpolkit reference manualturn1search4
- The final enforcement path must cover both IPv4 and IPv6. Otherwise an IPv6-capable network can bypass an IPv4-only policy.
- Device identity must be treated as evidence with confidence, not as an unquestionable MAC address. Randomized MACs, address changes, spoofing, and topology changes must be represented explicitly before a device becomes an enforcement target.
- Enforcement must be topology-aware. Discovering a device is not equivalent to being able to control its traffic; the application must prove that the managed host is actually on the relevant traffic path.
- Desired policy and actual kernel state must be separate concepts. A restart, external firewall change, interface change, or topology change must trigger reconciliation rather than silently assuming that the previous state still exists.
- The GUI must remain an unprivileged client of the backend/service layer. Security-sensitive operations must not depend on GTK callback code or direct root command execution.

These constraints change the execution order: verification → network truth → identity/topology → canonical state/policy → privileged boundary → enforcement → observability/recovery → advanced controls → release.

---

# 2. Current baseline

## Completed foundations

- [x] GTK4 is the only active UI target.
- [x] CLI/TUI development direction retired.
- [x] Linux-only runtime direction established.
- [x] Shared application state and background-task architecture.
- [x] Passive Linux neighbor discovery.
- [x] Scapy ARP discovery.
- [x] Hybrid discovery and reconciliation.
- [x] Bounded Nmap deep inventory.
- [x] Hostname, vendor, device-type, and OS-hint enrichment.
- [x] Persistent MAC/IP observation history.
- [x] IP-change tracking and observation history.
- [x] Enrichment changes preserved as historical observations.
- [x] Linux neighbor monitoring with debouncing.
- [x] Direct online/offline transitions for known devices.
- [x] Discovery reconciliation retained as the safety path.
- [x] Gateway/inline enforcement topology model.
- [x] IPv4-forwarding validation for gateway mode.
- [x] Enforcement disabled by default.
- [x] Local-host and gateway self-lockout protection.
- [x] Atomic nftables named-set updates.
- [x] Non-destructive nftables rollback.
- [x] Existing-flow semantics without an established/related bypass.
- [x] Profile semantics and policy precedence foundations.
- [x] Persistent device-observation database model.
- [x] Dedicated GTK page modules.
- [x] GTK page cleanup contract and main-window cleanup.
- [x] Architecture regression coverage.
- [x] Linux firewall network-namespace integration coverage.
- [x] Existing TCP-flow block/recovery integration coverage added.
- [x] CachyOS/Arch installation and venv workflow documented.
- [x] GPL-3.0-or-later metadata aligned.

## Current verification gap

The implementation is ahead of the runtime verification in several security-sensitive areas. Baseline commit `cb0f20083d542cb455c4fbb11b94d5b7f12caf90` passed all five jobs in [CI run 36848741182](https://github.com/Praxis1071/NetFather/actions/runs/36848741182), including both privileged nftables tests. This verifies that baseline, not subsequent changes.

See [the discovery/presence contribution plan](docs/CONTRIBUTION-PLAN.md) for the current scoped work and verification limits.

- [x] Verify the baseline firewall integration suite in GitHub Actions (run 36848741182).
- [x] Verify the baseline existing TCP-flow test in privileged CI (run 36848741182).
- [ ] Finish end-to-end policy-to-firewall verification.
- [ ] Finish complete GTK background-task and lifecycle coverage.
- [ ] Finish failure-injection and firewall recovery integration tests.

---

# 3. Phase I — Finish the network core

## 3.1 Reliable device identity

### Goal

A device must remain the same logical device when DHCP changes its IP address.

### Tasks

- [x] MAC-backed device identity.
- [x] Persistent IP history.
- [x] Observation source and confidence.
- [x] Hostname/vendor/type/OS enrichment history.
- [x] DHCP and manual IP-change tracking.
- [ ] Handle randomized Wi-Fi MAC addresses where evidence permits.
- [ ] Define identity confidence and conflict-resolution rules.
- [ ] Add explicit identity merge/split safeguards.
- [ ] Prevent ambiguous identities from silently becoming enforcement targets.

### Done when

- DHCP changes do not create accidental duplicate devices.
- Historical observations survive application restarts.
- Enforcement follows the current device address safely.
- Identity conflicts are visible and explainable.

---

## 3.2 Discovery expansion

### Goal

Provide a layered local-network inventory without turning every scan into an expensive or uncontrolled operation.

### Tasks

- [x] Passive neighbor discovery.
- [x] Active ARP discovery.
- [x] Hybrid reconciliation.
- [x] Bounded Nmap host discovery.
- [x] Bounded TCP/UDP/service/version/OS inventory.
- [ ] IPv6/NDP discovery.
- [ ] DHCP lease enrichment.
- [ ] NetworkManager device/connection signals.
- [ ] mDNS/LLMNR/NetBIOS enrichment where appropriate.
- [ ] Persistent service and port history.
- [~] Discovery source and deep-inventory warnings reach snapshots and the GTK status message; graphical runtime verification remains open.
- [~] Preserve positive observations and suppress missing-device transitions on partial/failed scans; cancellation remains open.
- [ ] Expand subprocess and error-path tests.

### Done when

Normal discovery remains useful without Nmap, deep scans stay bounded, discovery sources are visible, and partial failures never destroy known device state.

---

## 3.3 Live presence and event propagation

### Goal

Provide fast online/offline state without trusting one transient neighbor-cache event as the complete truth.

### Tasks

- [x] Linux neighbor monitoring.
- [x] NUD-state classification.
- [x] Debouncing.
- [x] Direct known-device presence transitions.
- [x] Discovery reconciliation safety path.
- [x] Monitor-thread exception isolation.
- [x] Safe shutdown of presence timers and threads.
- [ ] Define canonical runtime event taxonomy.
- [ ] Add central runtime event bus.
- [~] Add source-to-service-to-SQLite presence integration tests; real kernel notification integration remains open.
- [~] Apply offline grace consistently to missing-device scans and removal hints; aging of STALE/DELAY/PROBE cache entries remains open.
- [ ] Persist presence transitions in the Events workspace.

### Done when

Presence updates quickly, transient events are reconciled safely, and one canonical event can be consumed by GUI, history, policy, and monitoring without duplicated business logic.

---

## Stabilization Gate I — Phase I hata ayıklama ve stabilizasyon

Phase I tamamlandıktan sonra bu kapı tamamlanmadan Phase II'ye geçilmez.

- [ ] Phase I'in tüm görevlerini uçtan uca doğrula.
- [ ] Hataları, exception/timeout durumlarını ve başarısızlık yollarını düzelt.
- [ ] IPv4/IPv6, discovery, identity ve presence kenar durumlarını test et.
- [ ] Regresyon testlerini ve mevcut test paketini çalıştır.
- [ ] CI sonuçlarını doğrula ve kalan sorunları gider.
- [ ] Yeniden başlatma ve temiz kapanış davranışını doğrula.
- [ ] Phase I kararlı ve doğrulanmış olmadan sonraki aşamaya geçme.

### Gate exit criteria

- [ ] Phase I kapsamındaki bilinen hatalar giderildi.
- [ ] Testler ve CI başarılı.
- [ ] Kritik regresyon veya veri kaybı riski bulunmuyor.
- [ ] Phase II'ye geçiş onaylandı.

---

# 4. Phase II — Complete the GTK4 product

## 4.0 Product UI/UX design system — visual direction

The GUI is a first-class part of the final product, not a cosmetic layer added after the networking work. NetFather should feel like a polished, trustworthy Linux-native network control center: technically powerful underneath, calm and immediately understandable on the surface.

### Design target

Use a GNOME-native GTK4 + Libadwaita control-center architecture as the visual foundation. GNOME's current HIG is explicitly designed around GTK4 and Libadwaita, and Libadwaita provides the adaptive navigation, split-view, sidebar, card, dark/light, and high-contrast primitives needed for this product.

The target aesthetic is modern, restrained, information-dense without being cluttered, and unmistakably a native Linux desktop application. Avoid generic web-dashboard styling, excessive rounded cards, gradients, neon/cyberpunk decoration, oversized hero areas, unnecessary animation, or decorative elements that compete with network state.

### Information architecture

The primary desktop navigation should use an adaptive sidebar/split-view. GNOME recommends sidebars when an application has several frequently accessed views, and Libadwaita provides the navigation split-view/sidebar pattern for this purpose.

Target workspace structure:

- **Overview** — concise network health, enforcement status, device counts, active policy state, recent events, and actionable warnings.
- **Devices** — the primary device-management workspace; list/grid when useful, with a detail pane for the selected device.
- **Discovery** — active/passive discovery controls, progress, capability warnings, source-aware results, and scan history.
- **Profiles** — reusable device-policy groups and assignment state.
- **Rules** — policy rules, schedules, priority, conflicts, and effective-policy explanation.
- **Topology** — evidence-based gateway, interface, bridge, VLAN, AP/client, and device relationships.
- **Monitoring** — traffic/accounting summaries, enforcement counters, and time-window statistics.
- **Events** — searchable/filterable chronological network, policy, identity, and enforcement history.
- **Settings** — application behavior, appearance, discovery capabilities, retention, and advanced configuration.

Keep navigation labels explicit and short. Use GNOME/Adwaita symbolic icons consistently; icons supplement labels rather than replacing important security-sensitive text.

### Main window composition

Desktop layout should use an adaptive split view:

**Sidebar → workspace → contextual detail/utility pane when needed**

The workspace should not become a permanent three-column dashboard. Use a second pane only when it materially improves a workflow, such as selecting a device and inspecting its details or reviewing a rule's effective policy. Libadwaita split views can collapse into navigation on narrow windows, so the same information architecture remains usable without a desktop-sized window.

### Visual hierarchy

- One clear page title and one primary action per workspace where practical.
- Prefer structured lists, boxed lists, tables/list rows, and restrained cards over a wall of independent floating cards.
- Use consistent spacing, typography, margins, and section headers throughout the application.
- Keep important network state visible near the relevant object: device presence, identity confidence, profile, effective policy, and enforcement state should not require hunting through unrelated pages.
- Make destructive or security-sensitive actions visually and textually explicit.
- Use progressive disclosure for advanced networking details so novice users are not overwhelmed while administrators can still inspect evidence and technical state.

### Security-state visual language

Security and network state must be immediately readable without relying on color alone.

- **Enforced / active:** clear semantic status with icon + text + optional accent.
- **Allowed / unrestricted:** neutral-positive presentation with explicit wording.
- **Blocked:** explicit blocked state with icon + text.
- **Warning / degraded:** warning icon + concise explanation + next action.
- **Unknown / unverified:** neutral warning state; never visually imply certainty.
- **Offline:** distinct presence state, separate from policy state.
- **Identity conflict:** prominent but non-alarming warning that prevents silent enforcement.
- **Enforcement unavailable:** explain why (topology, privilege, service, interface, or kernel state) instead of merely showing a generic error.

Do not encode meaning by color alone; status icons, labels, descriptions, and accessible names must remain understandable in dark, light, and high-contrast appearances. Prefer standard Libadwaita widgets over bespoke styling.

### Devices experience

Devices should be the visual center of NetFather's management workflow.

Each device row should make the most useful facts scannable: name, device type/vendor when known, current IP, presence, identity confidence, assigned profile, and enforcement state. Selecting a device opens a coherent detail view with identity evidence, MAC/IP history, services, effective policy, enforcement information, traffic summary, and recent events.

The detail view should separate **what NetFather observed**, **what NetFather inferred**, **what policy says**, and **what the kernel is actually enforcing**. This mirrors the backend distinction between evidence, desired state, and actual state and prevents the GUI from presenting assumptions as facts.

### Profiles and Rules experience

Profiles should look like reusable policy objects rather than generic settings pages. Rules should be presented as ordered, understandable policy entries with their scope, action, schedule, and priority visible at a glance.

The rule editor must make the resulting behavior obvious before saving. Include a readable summary of affected devices/profile, action, service/destination scope, schedule, and precedence. Conflict warnings and the final effective-policy explanation should be part of the normal workflow rather than hidden diagnostic output.

### Discovery and topology experience

Discovery should communicate progress and evidence instead of appearing as a mysterious scan button. Show the active stage, cancellation, capabilities/privileges, partial results, source, and enrichment status.

Topology should prioritize truth over visual spectacle. Relationships must be visibly distinguished as **observed**, **inferred**, or **unknown**. The graph should remain readable with many devices and provide a detail path back to the selected device rather than turning into an ornamental network diagram.

### Monitoring and Events experience

Monitoring should prioritize trends and decisions over decorative charts. Use compact summaries, meaningful time ranges, clear units, and measured-vs-estimated labeling. Events should use a dense but readable chronological layout with filtering by device, event type, severity/state, and time.

### Adaptive, accessibility, and lifecycle requirements

- Use Libadwaita adaptive navigation/split-view patterns rather than maintaining a desktop-only layout.
- Support narrow windows without losing access to any primary workspace or critical action.
- Support system, light, dark, and high-contrast appearance correctly; avoid hard-coded colors that break semantic states.
- Provide keyboard navigation and accessible names/roles for all interactive controls.
- Never communicate a security decision only through animation or transient notification.
- Provide consistent loading, empty, unavailable, warning, permission-denied, and failure states.
- Long-running discovery/enforcement operations must expose progress/cancellation without freezing the UI.
- UI updates must follow GTK main-thread/lifecycle rules and never leave stale callbacks after a page or application is closed.
- Motion should be purposeful and subtle; it must never obscure network state or become a permanent visual effect.

### GUI quality gate

The GUI is considered complete only when the application looks and behaves as one coherent product across Devices, Discovery, Profiles, Rules, Topology, Monitoring, Events, and Settings. A feature is not visually complete merely because its widgets render: it must have correct hierarchy, loading/empty/error states, adaptive behavior, accessibility, keyboard support, lifecycle safety, and clear communication of security/network state.

### Research basis

The visual direction is based primarily on the current GNOME HIG and Libadwaita documentation rather than a generic web-dashboard template. The key patterns are sidebars for frequent multi-view navigation, adaptive split/navigation views for narrow windows, standard Libadwaita cards/lists, and built-in light/dark/high-contrast support.

Research references:
- GNOME Human Interface Guidelines — https://developer.gnome.org/hig/
- GNOME sidebar guidance — https://developer.gnome.org/hig/patterns/nav/sidebars.html
- Libadwaita adaptive layouts — https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/adaptive-layouts.html
- Libadwaita sidebar reference — https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.Sidebar.html
- Libadwaita styles and appearance — https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/styles-and-appearance.html
- Libadwaita style classes — https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/style-classes.html

---

## 4.1 Application shell

### Tasks

- [x] Separate GTK workspace modules.
- [x] Shared page cleanup contract.
- [x] Main-window cleanup.
- [~] Persistent system/light/dark selection with native GTK colors; desktop and high-contrast graphical verification remain open.
- [~] English/Turkish/Azerbaijani UI catalogs and localized About/contributor credits; graphical text/layout QA remains open.
- [~] Manual navigation collapse, two-column metrics and stacked Profile/Rule forms; automatic adaptive navigation and full narrow-window QA remain open.
- [ ] Finish useful Libadwaita migration.
- [ ] Adaptive navigation.
- [ ] Narrow-window layouts.
- [ ] Consistent loading, empty, and error states.
- [ ] Consistent destructive-action confirmation.
- [ ] Keyboard navigation and accessibility pass.
- [ ] Background-task cancellation UI.
- [ ] Audit all GTK callbacks for main-thread safety.
- [ ] Keep network work off the GTK main thread.
- [ ] Keep device/status presentation free of emoji indicators.

### Done when

Every workspace remains responsive during discovery and policy operations, closes cleanly, works at narrow widths, and presents understandable errors.

---

## 4.2 Devices workspace

### Goal

Make Devices the main place where the user understands and manages network devices.

### Tasks

- [x] Display discovered devices.
- [x] Show identity and enrichment data.
- [x] Show current presence.
- [ ] Device detail view.
- [ ] Rename device.
- [ ] Edit device metadata.
- [ ] Show MAC/IP history.
- [ ] Show discovery source and confidence.
- [ ] Show discovered services when available.
- [ ] Show assigned profile.
- [ ] Show effective policy.
- [ ] Show enforcement state.
- [ ] Show recent device events.
- [ ] Safe forget/remove workflow.
- [ ] Visible identity-conflict handling.

### Done when

A user can understand what a device is, whether it is online, which profile controls it, what policy applies, and what happened recently from one coherent workflow.

---

## 4.3 Network Discovery workspace

### Tasks

- [x] Discovery modes.
- [x] Background scanning.
- [ ] Scan progress and stages.
- [ ] Scan cancellation.
- [ ] Capability and privilege warnings.
- [ ] Source-aware results.
- [ ] Deep-inventory presentation.
- [ ] Per-device enrichment details.
- [ ] Scan history.
- [ ] Clear authorization feedback for privileged Nmap operations.

---

## 4.4 Network Topology workspace

### Goal

Show observed network relationships without inventing unsupported topology.

### Tasks

- [x] Gateway-centered topology foundation.
- [ ] Live device join/leave updates.
- [ ] Presence-driven topology updates.
- [ ] Interface relationships.
- [ ] Bridge relationships.
- [ ] VLAN relationships where observed.
- [ ] AP/client relationships where observed.
- [ ] Distinguish observed and inferred relationships.
- [ ] Keep unknown relationships explicitly unknown.

### Done when

Topology is evidence-based and updates as devices enter and leave the managed network.

---

## Stabilization Gate II — Phase II hata ayıklama ve stabilizasyon

Phase II tamamlandıktan sonra bu kapı tamamlanmadan Phase III'e geçilmez.

- [ ] Tüm GTK workspace'lerini uçtan uca test et.
- [ ] Loading, empty, error, permission ve cancellation durumlarını doğrula.
- [ ] Dar pencere, lifecycle ve arka plan görevlerini test et.
- [ ] Stale callback, thread/lifecycle ve kaynak temizleme sorunlarını gider.
- [ ] GUI regresyon testlerini ve CI sonuçlarını doğrula.
- [ ] Kritik kullanıcı akışlarında kalan hataları düzelt.
- [ ] Phase II kararlı ve doğrulanmış olmadan sonraki aşamaya geçme.

### Gate exit criteria

- [ ] Phase II kapsamındaki bilinen hatalar giderildi.
- [ ] Kritik GUI akışları ve yaşam döngüsü kararlı.
- [ ] Testler ve CI başarılı.
- [ ] Phase III'e geçiş onaylandı.

---

# 5. Phase III — Profiles and policy system

## 5.1 Profiles

### Goal

Allow reusable policy groups to control multiple devices.

### Tasks

- [x] Backend profile model.
- [x] Unrestricted / controlled / blocked semantics.
- [x] Policy precedence foundation.
- [ ] Complete profile creation.
- [ ] Complete profile editing.
- [ ] Change profile mode.
- [ ] Safe profile deletion.
- [ ] Assign and unassign devices.
- [ ] Show effective profile state.
- [ ] Show profile activity/history.
- [ ] Prevent unsafe deletion while devices are assigned.

### Done when

A user can create a profile, assign devices, change its behavior, and understand exactly what those devices receive.

---

## 5.2 Rules and schedules

### Goal

Turn profiles into explicit, predictable access policies.

### Tasks

- [ ] Rule creation.
- [ ] Rule editing.
- [ ] Rule deletion.
- [ ] Enable/disable.
- [ ] Rule priority.
- [ ] Allow rules.
- [ ] Block rules.
- [ ] Service/port targeting where supported.
- [ ] Destination/network targeting where supported.
- [ ] Explicit controlled-mode default-deny semantics.
- [ ] Explicit block-over-allow precedence.
- [ ] Overnight schedules.
- [ ] Multiple schedule windows.
- [ ] Time-zone handling.
- [ ] Conflict detection.
- [ ] Human-readable effective-policy explanation.
- [ ] Next-transition display.

### Done when

For every device NetFather can explain which profile applies, which rules are active, which rule wins, whether traffic is currently allowed, and when the next transition occurs.

---

## Stabilization Gate III — Phase III hata ayıklama ve stabilizasyon

Phase III tamamlandıktan sonra bu kapı tamamlanmadan Phase IV'e geçilmez.

- [ ] Profile ve rule CRUD akışlarını uçtan uca test et.
- [ ] Priority/precedence, allow/block ve controlled-mode davranışlarını doğrula.
- [ ] Schedule, overnight, timezone ve conflict kenar durumlarını test et.
- [ ] Effective-policy sonuçlarının deterministik ve açıklanabilir olduğunu doğrula.
- [ ] Policy değişikliklerinin mevcut state ile tutarlılığını kontrol et.
- [ ] Regresyon testlerini ve CI sonuçlarını doğrula.
- [ ] Policy katmanında kalan hataları düzelt.
- [ ] Phase III kararlı ve doğrulanmış olmadan enforcement aşamasına geçme.

### Gate exit criteria

- [ ] Politika davranışı deterministik ve testlerle doğrulanmış.
- [ ] Bilinen kritik policy hatası kalmamış.
- [ ] Testler ve CI başarılı.
- [ ] Phase IV'e geçiş onaylandı.

---

# 6. Phase IV — Real traffic enforcement

## 6.1 Enforcement safety gate

### Goal

Never imply that discovering another device automatically gives NetFather control over its internet traffic.

### Tasks

- [x] Explicit enforcement topology.
- [x] Gateway topology.
- [x] Inline topology.
- [x] IPv4 forwarding validation for gateway mode.
- [x] Reject unverified/host remote enforcement.
- [x] Enforcement disabled by default.
- [x] Protect local IPv4 addresses.
- [x] Protect gateway address.
- [ ] Add explicit interface/admin-host safeguards.
- [ ] Stronger enforcement-target validation.
- [ ] Preflight enforcement preview.
- [ ] User-visible enforcement-path explanation.
- [ ] Safe failure state when topology changes.

### Done when

NetFather refuses unsafe enforcement instead of guessing whether the current machine is a valid enforcement point.

---

## 6.2 nftables enforcement engine

### Goal

Make packet-level enforcement atomic, isolated, observable, and recoverable.

### Tasks

- [x] Dedicated NetFather nftables table.
- [x] Named blocking set.
- [x] Atomic set updates.
- [x] Preserve unrelated firewall tables.
- [x] Preserve NetFather counters during normal updates.
- [x] Non-destructive rollback.
- [x] Self-lockout protection.
- [x] Existing-flow semantics.
- [x] Network-namespace integration coverage.
- [x] Baseline nftables runtime CI verification (run 36848741182); new contributions require their own CI verification.
- [ ] Failure injection during policy application.
- [ ] Prove pre-existing NetFather state survives a failed update.
- [ ] Prove unrelated nftables state remains untouched.
- [ ] Persist and restore enforcement state across restart.
- [ ] Reconcile desired policy with actual nftables state.
- [ ] Detect external modification of the NetFather table.
- [ ] Add safe repair/reapply workflow.

### Done when

Every policy transition is atomic, observable, recoverable, repeatable, and isolated from unrelated firewall state.

---

## 6.3 Existing flows and conntrack

### Tasks

- [x] No blanket established/related accept bypass.
- [x] Baseline existing TCP-flow block/recovery integration test passed in privileged CI (run 36848741182).
- [x] Verify baseline existing-flow test in privileged CI (run 36848741182).
- [ ] Add UDP behavior coverage.
- [ ] Document expected conntrack behavior.
- [ ] Decide whether explicit conntrack cleanup is ever required.
- [ ] Verify recovery without restarting applications.

### Done when

Block and recovery behavior is documented and tested for both new and already-open flows.

---

## Stabilization Gate IV — Phase IV hata ayıklama ve stabilizasyon

Phase IV tamamlandıktan sonra bu kapı tamamlanmadan Phase V'e geçilmez.

- [ ] Policy → target → topology → privileged service → firewall → kernel zincirini uçtan uca test et.
- [ ] IPv4 ve IPv6 enforcement yollarını doğrula.
- [ ] Self-lockout, gateway ve yanlış hedef korumalarını test et.
- [ ] Başarısız transaction, rollback ve recovery senaryolarını test et.
- [ ] Existing TCP/UDP flow davranışını doğrula.
- [ ] External firewall değişikliği, restart ve topology değişikliği senaryolarını test et.
- [ ] Gerçek kernel state ile desired state tutarlılığını doğrula.
- [ ] Kritik enforcement hatalarını gider ve CI sonuçlarını doğrula.
- [ ] Phase IV kararlı ve güvenli olmadan sonraki aşamaya geçme.

### Gate exit criteria

- [ ] Desteklenen enforcement yolları integration testleriyle doğrulandı.
- [ ] Kritik güvenlik/regresyon sorunu kalmadı.
- [ ] Recovery ve rollback davranışı doğrulandı.
- [ ] Testler ve CI başarılı.
- [ ] Phase V'e geçiş onaylandı.

---

# 7. Phase V — Monitoring and event history

## 7.1 Monitoring

### Goal

Provide useful traffic visibility without making continuous Python packet capture the default telemetry design.

### Tasks

- [x] Linux interface-counter foundation.
- [ ] Device-level traffic accounting.
- [ ] Per-device upload/download totals.
- [ ] Active connection summaries where appropriate.
- [ ] Enforcement counters.
- [ ] Profile-level traffic summaries.
- [ ] Time-window statistics.
- [ ] Efficient counter collection.
- [ ] Distinguish measured data from estimates.

Preferred telemetry sources are nftables counters, Linux interface counters, conntrack information, and tc statistics.

---

## 7.2 Events and audit history

### Goal

Make important network, policy, and enforcement changes traceable.

### Tasks

- [x] Persistent event foundation.
- [ ] Canonical event taxonomy.
- [ ] Central runtime event bus.
- [ ] Device discovered.
- [ ] Device online/offline.
- [ ] IP changed.
- [ ] Identity enriched.
- [ ] Profile changed.
- [ ] Rule changed.
- [ ] Policy activated/deactivated.
- [ ] Firewall applied.
- [ ] Firewall rejected.
- [ ] Firewall recovered.
- [ ] Enforcement topology changed.
- [ ] Application/service startup and shutdown.
- [ ] Event filtering.
- [ ] Event retention policy.

### Done when

A user can see what happened, when it happened, which device was affected, and whether enforcement succeeded.

---

## Stabilization Gate V — Phase V hata ayıklama ve stabilizasyon

Phase V tamamlandıktan sonra bu kapı tamamlanmadan Phase VI'ya geçilmez.

- [ ] Monitoring ve event üretimini uçtan uca doğrula.
- [ ] Counter, accounting ve event history tutarlılığını kontrol et.
- [ ] Eksik, duplicate veya yanlış sıradaki eventleri tespit et ve düzelt.
- [ ] Ölçülen ve tahmini verilerin doğru ayrıldığını doğrula.
- [ ] Uzun süreli çalışma ve kaynak tüketimini kontrol et.
- [ ] GUI'deki monitoring/events state'inin backend ile tutarlı olduğunu doğrula.
- [ ] Regresyon testlerini ve CI sonuçlarını doğrula.
- [ ] Phase V kararlı olmadan bandwidth aşamasına geçme.

### Gate exit criteria

- [ ] Monitoring ve event history güvenilir.
- [ ] Kritik veri tutarsızlığı veya event kaybı kalmadı.
- [ ] Testler ve CI başarılı.
- [ ] Phase VI'ya geçiş onaylandı.

---

# 8. Phase VI — Bandwidth control

## Linux tc

### Goal

Add bandwidth management only where the traffic topology makes it technically meaningful.

### Tasks

- [ ] Design tc architecture for supported gateway/inline layouts.
- [ ] Define per-device bandwidth limits.
- [ ] Define upload/download semantics.
- [ ] Apply limits using stable device identity.
- [ ] Schedule bandwidth profiles.
- [ ] Add safe rollback.
- [ ] Add namespace/integration tests.
- [ ] Show bandwidth state in GTK.
- [ ] Document topology and hardware limitations.

### Done when

A configured limit is actually enforced at the supported traffic path and can be safely removed and recovered.

---

## Stabilization Gate VI — Phase VI hata ayıklama ve stabilizasyon

Phase VI tamamlandıktan sonra bu kapı tamamlanmadan Phase VII'ye geçilmez.

- [ ] tc yapılandırmasını ve desteklenen topology'leri uçtan uca test et.
- [ ] Upload/download limitlerinin doğru hedefe uygulandığını doğrula.
- [ ] Schedule, rollback ve recovery senaryolarını test et.
- [ ] Firewall ve tc state'lerinin birbirini bozmadığını doğrula.
- [ ] Namespace/integration testlerini çalıştır.
- [ ] Kaynak temizliği ve tekrar uygulama davranışını doğrula.
- [ ] Regresyon testlerini ve CI sonuçlarını doğrula.
- [ ] Phase VI kararlı olmadan privileged-service aşamasına geçme.

### Gate exit criteria

- [ ] Desteklenen bandwidth kontrol yolları doğrulandı.
- [ ] Rollback/recovery güvenilir.
- [ ] Testler ve CI başarılı.
- [ ] Phase VII'ye geçiş onaylandı.

---

# 9. Phase VII — Privileged service architecture

## D-Bus + polkit

### Goal

Keep the GTK process unprivileged while exposing only narrowly scoped privileged network operations.

### Tasks

- [ ] Define privileged operation API.
- [ ] Define D-Bus service boundary.
- [ ] Define polkit actions.
- [ ] Separate discovery privilege from enforcement privilege.
- [ ] Prevent arbitrary command execution through the service.
- [ ] Add authorization tests.
- [ ] Add service lifecycle handling.
- [ ] Recover cleanly if the service disappears.
- [ ] Keep GUI independent from root execution.

Target architecture:

**GTK4 application → D-Bus → privileged NetFather service → nftables / tc / limited privileged discovery**

### Done when

The normal GTK process never needs to run as root.

---

## Stabilization Gate VII — Phase VII hata ayıklama ve stabilizasyon

Phase VII tamamlandıktan sonra bu kapı tamamlanmadan Phase VIII'e geçilmez.

- [ ] D-Bus API sınırlarını ve yetkili işlemleri uçtan uca test et.
- [ ] polkit yetkilendirme ve reddedilen erişimleri doğrula.
- [ ] GTK sürecinin root gerektirmediğini doğrula.
- [ ] Servis çökmesi, yeniden başlaması ve bağlantı kopması senaryolarını test et.
- [ ] Yetki sınırı ihlali ve arbitrary-command risklerini kontrol et.
- [ ] Service lifecycle ve recovery davranışını doğrula.
- [ ] Regresyon testlerini ve CI sonuçlarını doğrula.
- [ ] Phase VII güvenli ve kararlı olmadan sonraki aşamaya geçme.

### Gate exit criteria

- [ ] Privileged boundary doğrulandı.
- [ ] Yetkilendirme ve recovery testleri başarılı.
- [ ] Kritik güvenlik açığı veya regresyon kalmadı.
- [ ] Phase VIII'e geçiş onaylandı.

---

# 10. Phase VIII — Reliability and security

## 10.1 Database and migration safety

- [x] ORM model registry.
- [x] Observation-table schema regression test.
- [x] Additive legacy SQLite schema upgrade regression coverage.
- [ ] Define explicit schema migration/versioning.
- [ ] Test upgrades across supported releases.
- [ ] Test interrupted migrations.
- [ ] Test backup/restore.
- [ ] Test database corruption/error recovery.
- [ ] Define event/observation retention.

## 10.2 Runtime state consistency

- [x] Thread-safe subscriptions in core discovery/state paths.
- [x] Presence monitor exception isolation.
- [x] Presence shutdown synchronization.
- [ ] Complete GTK main-thread marshalling audit.
- [ ] Isolate listener exceptions consistently.
- [ ] Prevent stale callbacks after shutdown.
- [ ] Background-task cancellation tests.
- [ ] Full window/service lifecycle integration tests.

## 10.3 Firewall recovery

- [x] Non-destructive rollback.
- [x] Rollback newline regression fixed.
- [x] Basic block/recovery namespace coverage.
- [ ] Failure injection.
- [ ] Preserve existing NetFather state after failure.
- [ ] Preserve unrelated firewall state after failure.
- [ ] Detect external firewall modifications.
- [ ] Recover after process crash.
- [ ] Recover after machine/network restart.
- [ ] Recover after privileged-service restart.

---

## Stabilization Gate VIII — Phase VIII hata ayıklama ve stabilizasyon

Phase VIII tamamlandıktan sonra bu kapı tamamlanmadan Phase IX'a geçilmez.

- [ ] Database migration, corruption ve recovery senaryolarını doğrula.
- [ ] Runtime state, thread-safety, cancellation ve shutdown davranışını test et.
- [ ] Firewall recovery/failure-injection senaryolarını tekrar doğrula.
- [ ] External state değişiklikleri ve restart sonrası recovery'yi test et.
- [ ] Güvenlik ve güvenilirlik regresyonlarını gider.
- [ ] Test ve CI sonuçlarını doğrula.
- [ ] Phase VIII kararlı olmadan testing aşamasına geçme.

### Gate exit criteria

- [ ] Reliability/security kapsamındaki bilinen kritik hatalar giderildi.
- [ ] Recovery ve lifecycle testleri başarılı.
- [ ] Testler ve CI başarılı.
- [ ] Phase IX'a geçiş onaylandı.

---

# 11. Phase IX — Testing strategy

Testing is part of the product, not a final cleanup step. Firewall and policy bugs can have real network consequences.

## Unit tests

- [x] Policy precedence.
- [x] Configuration validation.
- [x] Identity observations.
- [x] Discovery reconciliation.
- [x] nftables transaction shape.
- [x] Self-lockout protection.
- [x] Architecture boundaries.
- [x] Database schema.
- [ ] Remaining edge cases.

## Integration tests

- [x] Linux network-namespace firewall path.
- [x] Block/recovery packet behavior.
- [~] Existing TCP connection across block/recovery.
- [ ] UDP behavior.
- [ ] Failed nftables transaction recovery.
- [ ] Unrelated firewall-state preservation.
- [ ] Live presence transitions.
- [ ] Discovery + identity + policy integration.
- [ ] Policy + firewall end-to-end integration.
- [ ] D-Bus/polkit integration.

## GUI tests

- [x] Architecture boundaries.
- [x] Page cleanup contract.
- [ ] Workspace lifecycle.
- [ ] Background-task cancellation.
- [ ] State subscription lifecycle.
- [ ] Profile workflows.
- [ ] Rule workflows.
- [ ] Device workflows.
- [ ] Topology live updates.
- [ ] Loading/empty/error states.

## CI

- [x] Python test matrix.
- [x] Editable-install and entrypoint coverage.
- [x] Privileged firewall integration job definition.
- [ ] Verify the latest integration suite with successful GitHub Actions runs.
- [ ] Keep privileged firewall failures diagnostically separate.
- [ ] Publish actionable failure diagnostics.

---

## Stabilization Gate IX — Phase IX hata ayıklama ve stabilizasyon

Phase IX tamamlandıktan sonra bu kapı tamamlanmadan release aşamasına geçilmez.

- [ ] Unit, integration, GUI ve CI testlerinin tamamını çalıştır.
- [ ] Test koleksiyon/çalıştırma hatalarını gider.
- [ ] Flaky testleri tespit edip düzelt.
- [ ] Privileged/network-namespace testlerini doğrula.
- [ ] Testlerin gerçek ürün davranışını yeterince kapsadığını kontrol et.
- [ ] Test altyapısının kendisinden kaynaklanan yanlış güven sinyallerini gider.
- [ ] Phase IX kapsamındaki tüm bilinen test sorunlarını çöz.
- [ ] Release aşamasına geçmeden önce CI'yi doğrula.

### Gate exit criteria

- [ ] Test stratejisi güvenilir ve tekrarlanabilir.
- [ ] Kritik test açığı veya flaky test kalmadı.
- [ ] Desteklenen CI matrisi başarılı.
- [ ] Phase X'e geçiş onaylandı.

---

# 12. Phase X — Release readiness

## Documentation

- [x] README project direction.
- [x] Security model.
- [x] Architecture documentation.
- [x] Technical-debt tracking.
- [ ] Keep README and ROADMAP synchronized.
- [ ] User guide.
- [ ] Administrator/gateway setup guide.
- [ ] Enforcement topology guide.
- [ ] Troubleshooting guide.
- [ ] Recovery guide.
- [ ] Supported Linux distribution documentation.
- [ ] Unsupported-topology documentation.

## Packaging

- [ ] Decide release packaging format.
- [ ] Validate GTK4/PyGObject native dependencies.
- [ ] Define Arch/CachyOS packaging path.
- [ ] Evaluate Flatpak feasibility.
- [ ] Evaluate additional Linux packaging only if maintainable.
- [ ] Decide whether ARM64 is a supported release target.
- [ ] If ARM64 is supported, build and test natively.
- [ ] Validate upgrade behavior.

## Stable-release security gate

Before a stable release:

- [ ] No known unsafe enforcement path.
- [ ] No accidental self-lockout.
- [ ] No destructive rollback.
- [ ] No privilege escalation through GUI actions.
- [ ] No policy bypass through existing flows.
- [ ] Identity changes cannot silently redirect enforcement.
- [ ] Recovery behavior is integration-tested.
- [ ] Supported enforcement topologies are documented.
- [ ] Release CI is green.

---

## Stabilization Gate X — Phase X release öncesi son hata ayıklama ve stabilizasyon

Phase X tamamlandıktan sonra final ürün kabulüne geçmeden önce bu kapı tamamlanır.

- [ ] Release candidate üzerinde tüm kritik akışları baştan sona test et.
- [ ] Kurulum, yükseltme, migration ve kaldırma senaryolarını doğrula.
- [ ] Desteklenen Linux ortamlarında release paketini doğrula.
- [ ] Security gate'lerin tamamını tekrar kontrol et.
- [ ] Dokümantasyon ile gerçek ürün davranışının tutarlı olduğunu doğrula.
- [ ] Bilinen kritik hata, regression veya release blocker bırakma.
- [ ] Son CI ve integration sonuçlarını doğrula.
- [ ] Bu kapı tamamlanmadan stable release/final acceptance aşamasına geçme.

### Gate exit criteria

- [ ] Release candidate kararlı.
- [ ] Kritik release blocker kalmadı.
- [ ] Testler ve CI başarılı.
- [ ] Final product acceptance gate'e geçiş onaylandı.

---

# 13. Active execution queue

This is the single source of truth for the practical implementation order. The order is derived from the final product goal and the Linux architecture constraints above. Later items may be developed in parallel only when doing so does not weaken an earlier dependency or safety guarantee.

## 1. Restore a trustworthy verification baseline

1. [x] Baseline test collection/syntax verified in upstream CI at `cb0f200`; local GTK dependency requirements remain explicit.
2. [~] Upstream Python 3.12/3.13/3.14 matrix passed in run 36848741182; this contribution needs fresh CI and GTK runtime verification.
3. [x] Verify the baseline Linux network-namespace firewall suite in privileged CI (run 36848741182).
4. [x] Verify the baseline existing-TCP-flow block/recovery test in privileged CI (run 36848741182).
5. [ ] Keep CI diagnostics separate for test, privilege, and environment failures.

## 2. Establish authoritative network truth

6. [~] Service/SQLite integration tests added for departure grace, recovery, DHCP changes, source failure, settings and shutdown; real kernel-event tests remain open.
7. [~] Removal hints and successful missing-device scans share the offline grace; stale-cache aging remains open.
8. [ ] Complete IPv6/NDP discovery and observation.
9. [ ] Add DHCP lease enrichment.
10. [ ] Integrate NetworkManager device/connection state where available.
11. [ ] Add mDNS/LLMNR/NetBIOS enrichment where appropriate.
12. [ ] Add persistent service/port history.
13. [~] Partial-result handling implemented across discovery, resolver, persistence and GTK feedback; cancellation remains open.
14. [~] Cover iproute2 missing/timeout/OS/exit failures, ARP privilege/target errors, independent-source fallback and warning propagation; remaining subprocess cases stay open.
15. [~] Failed/incomplete source cycles preserve last-known device state and identity; broader cancellation/topology/database failure guarantees remain open.

## 3. Make device identity and topology enforcement-safe

16. [ ] Complete randomized Wi-Fi MAC handling where evidence permits.
17. [ ] Define identity confidence and conflict-resolution rules.
18. [ ] Add explicit identity merge/split safeguards.
19. [ ] Prevent ambiguous identities from silently becoming enforcement targets.
20. [ ] Complete interface/admin-host/gateway protection.
21. [ ] Strengthen topology detection and validation.
22. [ ] Distinguish observed, inferred, and unknown topology relationships.
23. [ ] Add topology-change detection and safe invalidation of enforcement state.
24. [ ] Prove supported gateway/inline enforcement paths in integration tests.

## 4. Establish one canonical runtime state and event model

25. [ ] Define the canonical runtime event taxonomy.
26. [ ] Implement the central runtime event bus.
27. [ ] Connect discovery, identity, presence, topology, policy, enforcement, and monitoring to the bus.
28. [ ] Persist important transitions in event history.
29. [ ] Complete GTK main-thread marshalling and listener-safety audit.
30. [ ] Prevent stale callbacks after shutdown.
31. [ ] Complete background-task cancellation tests.
32. [ ] Complete application/window/service lifecycle integration tests.

## 5. Build and verify the deterministic policy engine

33. [ ] Complete profile creation/editing/mode changes.
34. [ ] Implement safe profile deletion and assignment/unassignment.
35. [ ] Define and test deterministic rule priority/precedence.
36. [ ] Implement allow/block rules.
37. [ ] Implement supported service/port and destination/network targeting.
38. [ ] Implement controlled-mode default-deny semantics.
39. [ ] Implement block-over-allow precedence.
40. [ ] Implement overnight/multiple schedule windows.
41. [ ] Implement timezone handling and next-transition calculation.
42. [ ] Implement rule conflict detection.
43. [ ] Implement human-readable effective-policy explanation.
44. [ ] Add complete policy-engine unit/property/edge-case coverage.
45. [ ] Ensure policy evaluation has no direct dependency on GTK or root privileges.

## 6. Complete the user-facing product model

46. [ ] Complete Devices detail workflow.
47. [ ] Add rename, metadata, MAC/IP history, discovery confidence, and services.
48. [ ] Show assigned profile, effective policy, enforcement state, and recent events.
49. [ ] Add safe device forget/remove and visible identity-conflict handling.
50. [ ] Complete Discovery progress, cancellation, capability/privilege warnings, source-aware results, deep inventory, and history.
51. [ ] Complete live Topology updates.
52. [ ] Add interface/bridge/VLAN/AP-client relationships where observed.
53. [ ] Complete Profiles and Rules workflows in GTK.
54. [ ] Add Profile/Rules/Devices/Topology GUI integration tests.
55. [ ] Finish useful Libadwaita migration and implement the GNOME-native adaptive navigation/split-view design system.
56. [ ] Implement the unified visual language across all workspaces: typography, spacing, icons, lists/cards, semantic status states, and restrained motion.
57. [ ] Standardize loading, empty, unavailable, error, destructive-confirmation, permission, keyboard, accessibility, and lifecycle states.
58. [ ] Complete the Overview workspace and make it the concise entry point for network health, enforcement state, device counts, and actionable warnings.
59. [ ] Complete the Devices visual/detail workflow with evidence, desired-policy, and actual-enforcement state clearly separated.
60. [~] Add localized Settings/About and shared English/Turkish/Azerbaijani UI catalogs; complete coherent visual workflows and graphical QA across all workspaces.
61. [~] Add persisted system/light/dark preferences, manual sidebar collapse and narrower metric/forms layouts; validate appearances, high contrast and full narrow-window behavior in GTK.
62. [ ] Perform a full GUI usability and visual-consistency pass at desktop and narrow widths.
63. [ ] Add GUI regression coverage for critical states, adaptive navigation, lifecycle cleanup, and security-state presentation.

## 7. Put all privileged network control behind a narrow service

64. [ ] Define the privileged operation API.
65. [ ] Implement the D-Bus service boundary.
66. [ ] Define least-privilege polkit actions.
67. [ ] Separate discovery privilege from enforcement privilege.
68. [ ] Prevent arbitrary command execution through the service.
69. [ ] Add D-Bus/polkit authorization tests.
70. [ ] Add privileged-service lifecycle and disconnect recovery.
71. [ ] Ensure the normal GTK process never requires root.
72. [ ] Re-run policy and integration tests through the service boundary.

## 8. Finish the real enforcement engine before exposing it as a product feature

73. [ ] Complete nftables failure-injection coverage.
74. [ ] Prove failed transactions preserve the previous NetFather state.
75. [ ] Prove unrelated nftables tables/rules remain untouched.
76. [ ] Complete IPv4 and IPv6 enforcement paths.
77. [ ] Add preflight enforcement preview.
78. [ ] Validate every enforcement target against identity confidence and topology.
79. [ ] Make topology changes fail safely instead of guessing.
80. [x] Implement desired-policy → kernel-state reconciliation after each enforcement sync and verify the kernel-owned nftables sets.
81. [x] Detect external modification of the NetFather firewall state through explicit, observation-only kernel-state drift checks.
82. [ ] Add safe repair/reapply workflow.
83. [ ] Persist desired enforcement state across restart.
84. [ ] Add TCP and UDP existing-flow behavior coverage.
85. [ ] Document conntrack behavior and determine when explicit cleanup is required.
86. [ ] Verify recovery without restarting affected applications.
87. [ ] Add full device → profile → rule → policy → firewall end-to-end tests.
88. [ ] Validate enforcement after application, service, interface, and machine restart.
89. [ ] Validate that no IPv4/IPv6 path bypasses the active policy.

## 9. Add observability before declaring enforcement production-ready

90. [ ] Implement device-level traffic accounting.
91. [ ] Add per-device upload/download totals.
92. [ ] Add active-connection summaries where appropriate.
93. [ ] Add enforcement counters.
94. [ ] Add profile-level traffic summaries.
95. [ ] Add time-window statistics.
96. [ ] Distinguish measured values from estimates.
97. [ ] Complete event coverage for discovery, identity, presence, topology, policy, firewall, recovery, and service lifecycle.
98. [ ] Add event filtering and retention.
99. [ ] Expose enforcement and event state coherently in GTK.

## 10. Harden persistence and recovery

100. [ ] Define explicit database schema versioning/migrations.
101. [ ] Test upgrades across supported releases.
102. [ ] Test interrupted migrations.
103. [ ] Test backup/restore.
104. [ ] Test database corruption/error recovery.
105. [ ] Define observation/event retention behavior.
106. [ ] Test firewall recovery after application restart.
107. [ ] Test recovery after machine/network restart.
108. [ ] Test recovery after privileged-service restart.
109. [ ] Complete the security-sensitive failure/recovery matrix.
110. [ ] Perform a dedicated identity → policy → enforcement safety review.

## 11. Add bandwidth control as an advanced enforcement capability

111. [ ] Design tc architecture for supported gateway/inline topologies.
112. [ ] Define per-device bandwidth limits and upload/download semantics.
113. [ ] Apply tc limits using stable device identity.
114. [ ] Add scheduled bandwidth profiles.
115. [ ] Add safe tc rollback and recovery.
116. [ ] Add namespace/integration coverage.
117. [ ] Expose bandwidth state in GTK.
118. [ ] Document topology and hardware limitations.

## 12. Finish release readiness

119. [ ] Keep README, architecture docs, technical debt, and ROADMAP synchronized.
120. [ ] Complete the end-user guide.
121. [ ] Complete administrator/gateway setup documentation.
122. [ ] Complete enforcement-topology documentation.
123. [ ] Complete troubleshooting and recovery guides.
124. [ ] Document supported Linux distributions and unsupported topologies.
125. [ ] Decide the primary release packaging format.
126. [ ] Validate GTK4/PyGObject native dependencies for releases.
127. [ ] Define and implement the Arch/CachyOS packaging path.
128. [ ] Evaluate Flatpak feasibility.
129. [ ] Decide whether ARM64 is a supported release target and test it if supported.
130. [ ] Validate upgrade behavior.
131. [ ] Run the complete security audit.
132. [ ] Run the complete integration test suite with green CI.
133. [ ] Verify every stable-release security gate.
134. [ ] Produce a release candidate.
135. [ ] Perform release-candidate validation.
136. [ ] Publish the stable release.

### Final product acceptance gate

NetFather is considered to have reached its final goal only when all of the following are true:

- [ ] Local devices are discoverable through layered, failure-tolerant discovery.
- [ ] Device identity survives normal address changes and ambiguous identity is surfaced safely.
- [ ] Live presence and topology state are observable and evidence-based.
- [ ] Devices can be organized and assigned reusable profiles.
- [ ] Rules and schedules produce deterministic, explainable effective policies.
- [ ] The application can prove whether the managed host is actually able to enforce those policies.
- [ ] The normal GTK process remains unprivileged.
- [ ] The privileged service exposes only narrowly authorized network operations.
- [ ] Real traffic enforcement works for all supported protocol paths, including IPv4 and IPv6.
- [ ] Enforcement is atomic, isolated, observable, recoverable, and reconciled with actual kernel state.
- [ ] Monitoring and event history show what happened and whether enforcement succeeded.
- [ ] Restart, crash, topology-change, and external-firewall-change recovery paths are tested.
- [ ] CI is green for the supported test and integration matrix.
- [ ] GUI visually and behaviorally meets the GNOME-native design system and adaptive/accessibility quality gate.
- [ ] Documentation accurately states supported topologies and limitations.

---
# 14. Definition of done

A NetFather feature is not complete simply because its UI exists.

For security-sensitive network features, completion requires:

**implementation + unit tests + integration tests + failure/recovery behavior + documentation + GUI state/feedback + privilege review + CI verification**

A feature remains **[~] partially complete** whenever the implementation exists but required runtime verification is still missing.

---

# 15. Long-term user experience

The final workflow should be simple even though the backend is technically complex:

**Discover → Understand → Name → Assign profile → Set rules → Schedule → Enforce → Observe → Recover safely**

The complexity belongs in NetFather's backend, not in the user's workflow.

The final product should be a trustworthy Linux-native control center for the user's own local network, while remaining explicit about what it can observe, where it can enforce policy, what evidence supports its decisions, and what happens when something fails.

---

## Roadmap maintenance rule

Whenever a significant implementation change lands:

1. Update the relevant checkbox.
2. Update exit criteria if the scope changed.
3. Update the Active execution queue.
4. Keep docs/TECHNICAL-DEBT.md focused on engineering findings.
5. Keep ROADMAP.md focused on product sequencing.
6. Never mark an enforcement/security item complete solely because a unit test passes when integration verification is required.
