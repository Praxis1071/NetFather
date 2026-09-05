# Architecture

NetFather katmanları:

1. **network/** — interface status, passive/active discovery, topology.
2. **manager/** — persistent device/profile/rule/event CRUD ve PolicyEngine.
3. **firewall/** — OS-specific enforcement; policy hesaplamaz.
4. **monitor/** — presence tracker ve traffic telemetry.
5. **scheduler/** — periyodik policy→firewall sync.
6. **core/service.py** — OS-native daemon startup helper.
7. **cli/** ve **tui/** — aynı manager/network katmanlarını kullanan UI'lar.

Bu ayrım firewall ayrıcalıklarını veri CRUD katmanından ayırır. Discovery sonucu doğrudan firewall komutu üretmez; önce DB kimliği ve PolicyEngine kararı oluşur.

## Device lifecycle

`scan_network` → `DeviceManager.reconcile_discovery` → Device + Event → `PolicyEngine` → `FirewallEngine`.

Online/offline kararı tek bir missed scan ile verilmez; `offline_after_seconds` grace period uygulanır.

## Database compatibility

v0.4.0 ek kolonları additive/idempotent SQLite migration ile ekler. Var olan device/profile/rule verileri korunur.
