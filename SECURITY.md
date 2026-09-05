# Security Policy

NetFather bir yerel ağ yönetim aracıdır. Yalnız yönetme yetkinizin bulunduğu ağlarda kullanın.

## Privileged operations

Active Scapy discovery, packet capture ve firewall enforcement OS'e göre root/admin/Npcap/BPF yetkisi gerektirebilir. NetFather varsayılan olarak firewall değişikliği yapmaz; gerçek enforcement açık `--apply` ile istenir.

## Firewall isolation

- Linux: yalnız `table inet netfather`
- Windows: yalnız firewall group `NetFather`
- macOS: yalnız PF anchor `com.apple/netfather`
- policy target: yalnız private/link-local IPv4

Başka firewall kurallarını global flush etmek tasarım dışıdır.

## Reporting

Güvenlik açığını public issue'da exploit ayrıntılarıyla yayınlamak yerine repository owner'a özel kanaldan bildirin. Reproduction için minimum gerekli bilgi, OS, NetFather sürümü ve ilgili log satırlarını paylaşın; kişisel MAC/IP bilgilerini anonimleştirin.
