# Discovery

## Passive

- Linux: `ip neigh`
- Windows: `Get-NetNeighbor`, fallback `arp -a`
- macOS: `arp -an`

Pasif mod paket göndermez; OS cache'inde olan komşuları okur.

## Active

Scapy Ethernet broadcast ARP sweep yalnız local IPv4 subnet üzerinde çalışır. Subnet OS prefix/netmask'ten türetilir; bilgi yoksa güvenli `/24` fallback kullanılır. `/16`'dan geniş active range reddedilir.

Scapy veya capture driver/yetkisi yoksa hybrid mod passive sonuca düşer.

## Metadata

Vendor yerel OUI DB'sinden; hostname reverse lookup'tan; device type vendor/hostname heuristic'inden gelir. OS detection açık olduğunda kısa ICMP TTL probe bir **hint** üretir; kesin fingerprint değildir.
