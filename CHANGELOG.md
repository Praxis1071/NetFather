# Changelog

## Unreleased — 0.5.x hardening

- Add persistent system/light/dark appearance preferences with immediate theme switching.
- Add system-language detection and English, Turkish and Azerbaijani UI catalogs, including all About text; language changes apply after restart.
- Add contributor Cavanşir Qurbanzadə (YoungLion) and GitHub profile to About while retaining the original developer and deriving the version from core metadata.
- Add a navigation toggle, two-column metric cards and stacked profile/rule forms; distinguish desired policy from actual protection in Dashboard labels.
- Separate Settings/About/theme modules, keep state imports independent of GTK, and fix label-dependent monitoring pause and live-presence switch state persistence.
- Roll back preference controls after save failures and include translation resources in wheel and PyInstaller releases.
- Distinguish failed discovery sources from successful empty scans and retain observations from independent sources.
- Preserve missing-device presence during partial scans and use the configured offline grace for runtime identity and persistence.
- Reconcile neighbor deletion/failure hints instead of creating immediate offline transitions; ignore FAILED/INCOMPLETE cache records as positive observations.
- Display partial/deep-scan warnings in Discovery and honor reconciliation settings for manual GUI scans.
- Add deterministic discovery/presence/SQLite integration and callback tests. Kernel-event and graphical runtime verification remain pending.

## 0.4.0

### Platform / release
- Windows, Linux ve macOS runtime desteği; x64 + ARM64 release matrix.
- Native PyInstaller build, architecture validation, smoke test ve SHA256 release assets.
- Windows redirected-console UTF-8 workflow/runtime fixleri.
- `.gitattributes` ile kaynak/YAML/Python satır sonlarını LF olarak standardize etme.

### Discovery / device lifecycle
- Passive OS neighbor cache + Scapy ARP active discovery; `passive|active|hybrid` modları.
- Local subnet inference ve bounded active-scan güvenliği.
- Hostname, vendor, device type ve opsiyonel TTL tabanlı OS hint.
- Yeni cihaz auto-register; MAC ile kalıcı tekrar tanıma.
- Grace-period tabanlı online/offline tracking ve TUI live refresh.
- Eski v0.x SQLite DB'leri için additive/idempotent schema migration.

### Management / policy
- Mevcut device naming, profile CRUD ve rule schedule altyapısı PolicyEngine altında birleştirildi.
- Effective ALLOW/BLOCK kararı ve BLOCK precedence.
- Topology, policy ve events CLI komutları.
- Discovery/firewall ayarlarını atomik kaydeden `settings` komutları.

### Firewall / daemon
- Linux nftables backend: yalnız `inet netfather` table.
- Windows Defender Firewall backend: yalnız `NetFather` rule group.
- macOS PF backend: `com.apple/netfather` anchor.
- Private/link-local target validation, dry-run default, explicit `--apply`, rollback.
- RuleScheduler + discovery/policy daemon loop.
- systemd / Windows Task Scheduler / macOS LaunchDaemon service helpers.

### Monitoring / audit / TUI
- Interface traffic counters ve opsiyonel Scapy packet sampling.
- Policy-aware allowed/blocked/unknown packet sample sınıflandırması.
- Device/profile/rule/firewall lifecycle audit events.
- TUI: Topology, gerçek Monitoring, Events ve genişletilmiş Settings/Devices/Discovery ekranları.

### Testing
- Cross-platform unit/PTY suite.
- Native release targets build öncesi test suite çalıştırır.
- Linux CI network namespace + veth + nftables + ping ile gerçek enforcement integration testi.
