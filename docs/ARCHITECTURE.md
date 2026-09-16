# Architecture

NetFather katmanları:

1. **gui/** — GTK4 masaüstü uygulaması, navigation ve kullanıcı etkileşimi.
2. **network/** — Linux interface status, passive/active discovery ve topology verisi.
3. **manager/** — persistent device/profile/rule/event CRUD ve PolicyEngine.
4. **firewall/** — Linux nftables enforcement; policy hesaplamaz.
5. **monitor/** — presence tracking ve traffic telemetry.
6. **scheduler/** — arka plan discovery/policy → firewall senkronizasyonu için servis katmanı.
7. **core/** — configuration, database, logging, platform ve Linux service yardımcıları.

GTK4 yalnızca presentation/application layer'dır. Ağ keşfi, politika değerlendirmesi ve firewall enforcement widget'ların içine taşınmaz; böylece aynı backend canlı GUI, scheduler ve testler tarafından güvenli şekilde kullanılabilir.

## Device lifecycle

`scan_network` → `DeviceManager.reconcile_discovery` → Device + Event → `PolicyEngine` → `FirewallEngine`.

Online/offline kararı tek bir missed scan ile verilmez; `offline_after_seconds` grace period uygulanır.

## Discovery lifecycle

Discovery arka planda çalıştırılabilir ve GUI ana thread'ini bloke etmemelidir. Sonuçlar tek bir reconciliation akışından DB'ye yazılır; GUI DB/model durumunu yeniler.

## Database compatibility

SQLite migration'ları additive/idempotent olmalıdır. Var olan device/profile/rule verileri korunur.

## Platform scope

NetFather yalnız Linux hedefler. Windows/macOS runtime katmanları, platforma özel firewall backend'leri ve eski CLI/TUI UI katmanları artık proje mimarisinin parçası değildir.
