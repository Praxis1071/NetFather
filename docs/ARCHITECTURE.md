# NetFather Architecture

NetFather Linux-only bir GTK4 masaüstü uygulamasıdır. UI, uygulama state'i ve ağ motoru birbirinden ayrılır; GTK sayfaları ağ/policy iş mantığını yeniden uygulamaz.

## Katmanlar

1. **gui/** — GTK4/Libadwaita hedefli presentation layer, navigation, page lifecycle ve background-task entegrasyonu.
2. **manager/** — device/profile/rule/event yönetimi ve policy kararları.
3. **network/** — interface bilgisi, discovery, identity, presence ve topology gözlemleri.
4. **firewall/** — nftables enforcement backend'i; policy kararı üretmez.
5. **monitor/** — Linux interface/traffic telemetry.
6. **scheduler/** — zamanlanmış policy → enforcement senkronizasyonu.
7. **core/** — configuration, database, logging, privileges ve ortak runtime servisleri.
8. **models/** — SQLAlchemy persistence modelleri.

Discovery sonucu doğrudan firewall komutu üretmez:

`network → manager/identity → PolicyEngine → FirewallEngine → firewall backend`

## GUI modül sınırları

Her büyük GTK workspace ayrı modüldedir:

- `gui/base_page.py` — ortak page primitive ve section helper.
- `gui/dashboard_page.py`
- `gui/discovery_page.py`
- `gui/devices_page.py`
- `gui/topology_page.py`
- `gui/profiles_page.py`
- `gui/rules_page.py`
- `gui/monitoring_page.py`
- `gui/events_page.py`
- `gui/state.py` — ortak application state.
- `gui/tasks.py` — background worker ve GTK ana-thread callback köprüsü.
- `gui/window.py` — yalnızca ana pencere/navigation composition.

Eski birleşik `gui/pages.py` modülü kaldırılmıştır. Bu sınır, tek bir GTK dosyasının büyüyerek tüm workspace'leri ve iş mantığını içine almasını önlemek için regression test ile korunur.

## Device lifecycle

`discovery → DeviceManager.reconcile_discovery → Device + Observation/Event → PolicyEngine → FirewallEngine`

Linux neighbor olayları bilinen cihazlar için hızlı online/offline geçişi sağlayabilir; debounced discovery reconciliation ve periyodik tarama güvenlik/safety reconciliation olarak kalır.

## Enforcement lifecycle

`effective policy → protected-IP filtering → topology validation → nftables named-set update`

Firewall backend'i yalnızca NetFather'ın `inet netfather` tablosunu yönetir. Normal policy değişiklikleri tabloyu yeniden oluşturmaz. Rollback de tabloyu silmek yerine yalnızca NetFather'ın blocking set'ini temizler.

Gerçek remote-device enforcement yalnızca trafik NetFather'ın doğrulanmış gateway/router/inline yolundan geçtiğinde anlamlıdır.

## Database

SQLite + SQLAlchemy kullanılır. Model registry `models/__init__.py` üzerinden tamamlanır ve `Database.init_db()` additive/idempotent migration uygular.

Kalıcı device identity için MAC/IP gözlemleri, discovery source, confidence ve enrichment geçmişi saklanır.

## Test architecture

Testler:

- unit tests: `tests/test_*.py`
- Linux firewall integration: `tests/integration/test_firewall_netns.py`
- architecture regression: `tests/test_architecture.py`

Firewall correctness yalnızca unit testlere bırakılmaz; network namespace integration testi gerçek nftables paket davranışını ve enforcement recovery yolunu doğrular.

## Privilege boundary

GTK uygulaması root olarak çalıştırılmamalıdır. Discovery/enforcement için gereken ayrıcalıklar mümkün olduğunca operasyon bazında sınırlandırılmalı ve uzun vadede D-Bus + polkit üzerinden ayrıcalıklı Linux servisine taşınmalıdır.

## Retired architectures

CLI ve TUI artık proje hedefi değildir. Windows/macOS runtime dalları da proje kapsamı dışındadır. Yeni özellikler GTK4 + Linux architecture sınırları içinde geliştirilmelidir.
