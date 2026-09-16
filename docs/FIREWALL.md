# Firewall Enforcement

## Güvenli varsayılan

`[firewall].enforcement_enabled = false`.

GTK4 uygulaması policy durumunu gösterebilir ve enforcement durumunu yönetebilir. Gerçek trafik değişikliği yalnızca açıkça etkinleştirilmiş Linux firewall enforcement üzerinden yapılır.

## Linux nftables

NetFather yalnız kendi `inet netfather` table'ını yönetir. `input`, `output` ve `forward` chain'lerinde blocked device IPv4 set'i uygulanır. Yeni ruleset önce `nft -c` ile doğrulanır. Apply başarısız olursa NetFather'ın önceki table durumu geri yüklenmeye çalışılır.

## Policy

Profile `blocked` veya aktif `block` rule → BLOCK. Aktif block, allow'dan önceliklidir. IP'si olmayan cihaz firewall target olamaz; ancak policy durumu GUI ve event kayıtlarında tutulur.

## Scope

Firewall katmanı yalnız Linux/nftables içindir. Windows Defender Firewall, macOS PF ve eski CLI firewall komutları desteklenmez.
