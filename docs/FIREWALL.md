# Firewall Enforcement

## Güvenli varsayılan

`[firewall].enforcement_enabled = false`.

```bash
netfather firewall sync
```

yalnız preview/dry-run üretir. Gerçek işlem:

```bash
netfather firewall sync --apply
```

## Linux nftables

NetFather yalnız `table inet netfather` oluşturur. `input`, `output` ve `forward` chain'lerinde blocked device IPv4 set'ini uygular. Yeni ruleset önce `nft -c` ile doğrulanır. Apply başarısız olursa mevcut NetFather table backup'ı geri yüklenmeye çalışılır.

## Windows

Kurallar Defender Firewall içinde `NetFather` group'unda inbound/outbound RemoteAddress block olarak oluşturulur. Rollback yalnız bu group'u kaldırır.

## macOS PF

Kurallar `com.apple/netfather` anchor'ına yüklenir. Sistem PF konfigürasyonunun bu anchor namespace'ini çağırması gerekir; macOS sürüm/kurulumuna göre admin doğrulaması önerilir.

## Policy

Profile `blocked` veya aktif `block` rule → BLOCK. Aktif block, allow'dan önceliklidir. IP'si olmayan cihaz firewall target olamaz ama policy durumu DB/TUI'da gösterilir.
