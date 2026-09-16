# Network Discovery

NetFather discovery yalnız Linux yerel ağları için tasarlanmıştır.

## Passive discovery

Linux neighbor table (`ip neigh`) okunur. Pasif mod paket göndermez; işletim sisteminin mevcut komşu cache'ini kullanır.

## Active discovery

Scapy Ethernet broadcast ARP sweep yalnız local IPv4 subnet üzerinde çalışır. Subnet OS interface/prefix bilgisinden türetilir; bilgi yoksa güvenli `/24` fallback kullanılır. `/16`'dan geniş active range reddedilir.

Scapy veya capture driver/yetkisi yoksa hybrid mod passive sonuca düşebilir.

## Metadata

Vendor yerel OUI DB'sinden; hostname reverse lookup'tan; device type vendor/hostname heuristic'inden gelir. OS detection açık olduğunda TTL tabanlı sonuç yalnızca bir **hint** olarak değerlendirilir; kesin fingerprint değildir.

## Lifecycle

Discovery sonuçları `DeviceManager.reconcile_discovery` üzerinden tek bir persistence akışına girer. Yeni cihazlar auto-register ayarı açıksa kaydedilir; daha önce tanınan cihazlar MAC üzerinden güncellenir. Uzun süre görülmeyen cihazlar grace period sonrasında offline işaretlenir.

## GUI integration

GTK4 discovery ekranı taramayı arka planda çalıştırmalı, ilerleme/durum bilgisini kullanıcıya göstermeli ve ana UI thread'ini bloke etmemelidir.
