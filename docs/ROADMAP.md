# NetFather Development Roadmap

## Proje Vizyonu

NetFather; Linux üzerinde kullanıcının kendi yerel ağındaki cihazları keşfedip tanımlamasını, cihazları kullanıcı profillerine bağlamasını ve bu cihazların internet/ağ erişimini zamanlama ve çeşitli politikalarla gerçek ağ trafiği seviyesinde yönetmesini sağlayan açık kaynaklı bir ağ yönetimi ve ebeveyn kontrol sistemidir.

Nihai akış:

**Yerel ağ keşfi → güvenilir cihaz kimliği → canlı ağ durumu → cihaz yönetimi → profiller → politikalar ve zamanlamalar → gerçek trafik yönetimi → izleme ve olay geçmişi**

## Temel Ürün İlkeleri

- Linux tek desteklenen işletim sistemi olacak.
- GTK4 + Libadwaita, NetFather'ın tek kullanıcı arayüzü olacak.
- GUI; kullanıcı dostu, anlaşılır, modern ve görsel olarak güçlü olacak.
- GUI bol seçenek sunacak ancak karmaşık görünmeyecek; gelişmiş ayarlar gerektiğinde kademeli olarak gösterilecek.
- Arayüzde temiz kartlar, durum göstergeleri, anlaşılır grafikler ve tutarlı bilgi hiyerarşisi kullanılacak.
- Hafif ve anlamlı animasyonlar kullanılacak: sayfa geçişleri, durum değişimleri, tarama ilerlemesi ve canlı ağ güncellemeleri gibi. Animasyonlar işlevselliği veya performansı engellemeyecek.
- Emoji kullanılmayacak; cihazlar ve durumlar profesyonel UI bileşenleriyle gösterilecek.
- GUI ile ağ motoru birbirinden bağımsız tutulacak.
- Gerçek ağ davranışı, yalnızca veritabanı veya GUI durumundan daha önemli olacak.
- Büyük değişikliklerden önce yedek alınacak; küçük ve anlamlı commitler yapılacak.

## Hedef Mimari

```text
GTK4 / Libadwaita
        │
Application State
        │
 ┌──────┼──────────────┐
 ▼      ▼              ▼
Device  Policy       Monitoring
Service Service       Service
        │
        ▼
     Network Core
 ┌──────┼──────────────┐
 ▼      ▼              ▼
Discovery Identity   Presence
        │
        ▼
    Enforcement
    ┌──────┴──────┐
    ▼             ▼
 nftables         tc
```

İlerleyen aşamalarda ayrıcalıklı ağ işlemlerinin GUI'den ayrılması ve D-Bus üzerinden Linux servisinde çalıştırılması hedeflenir:

```text
netfather-gui
      │ D-Bus
      ▼
netfather.service
  ├─ discovery
  ├─ policy
  ├─ nftables
  └─ tc
```

## Aşama 0 — Mimari Temizlik ve Temel

- Linux-only yapının korunması.
- Eski CLI/TUI, Windows/macOS ve kullanılmayan runtime kalıntılarının temizlenmesi.
- Dokümantasyonun gerçek mimariyle eşleştirilmesi.
- Test yapısının ve CI'ın Linux + GTK4 hedefiyle uyumlu tutulması.
- GUI, servis ve core arasında net sınırlar oluşturulması.

## Aşama 1 — Application Core

- GTK4/Libadwaita uygulama yaşam döngüsü.
- Merkezi application state.
- Navigation/page sistemi.
- Ortak hata, bildirim ve dialog altyapısı.
- Uzun süren işlemler için UI'ı kilitlemeyen background task sistemi.
- Worker sonuçlarının güvenli şekilde GTK ana thread'ine aktarılması.
- GUI'nin doğrudan ağ motoru detaylarına bağımlı olmaması.

## Aşama 2 — Device Identity

IP adresi cihazın kalıcı kimliği olarak kullanılmayacak.

Cihaz kimliği için:

- Stabil dahili device ID.
- MAC adresi ve MAC geçmişi.
- IP ve IP geçmişi.
- Hostname.
- Vendor.
- Interface.
- İlk ve son görülme zamanı.
- Online/offline durumu.
- Identity confidence.
- Kimlik değişikliği geçmişi.
- Keşif kaynağı bilgisi.

Hedef: aynı fiziksel cihazın IP değişse bile doğru cihaz olarak tanınması.

## Aşama 3 — Discovery 3.0

Modüler gözlem kaynakları:

- Linux neighbor table.
- Scapy ARP discovery.
- ICMP/ping discovery.
- Hostname çözümleme.
- MAC/vendor bilgisi.
- NetworkManager/libnm bilgileri.
- DHCP bilgileri mümkün olduğunda.
- Wi-Fi istemci bilgileri mümkün olduğunda.

Discovery sonucu tek bir resolver katmanında birleştirilecek ve Device Identity sistemine aktarılacak.

Yeni olaylar:

- `NEW_DEVICE_DETECTED`
- `DEVICE_ONLINE`
- `DEVICE_OFFLINE`
- `DEVICE_CHANGED`
- `DEVICE_IDENTITY_UPDATED`

Yeni cihaz algılandığında mümkün olan zenginleştirme işlemleri otomatik çalışacak.

## Aşama 4 — Live Network State

- Sürekli arka plan ağ gözlemi.
- Online/offline takibi.
- Yeni/kaybolan cihaz tespiti.
- Canlı event bus.
- Discovery geçmişi.
- Cihaz değişikliklerinin GUI'ye anlık yansıtılması.
- NetworkManager sinyallerinin uygun yerlerde kullanılması.

## Aşama 5 — GTK4 / Libadwaita GUI

Ana bölümler:

- Dashboard.
- Network Discovery.
- Devices.
- Network Topology.
- Profiles.
- Rules.
- Monitoring.
- Events.
- Settings.

GUI tasarım hedefleri:

- Modern Linux masaüstü görünümü.
- Kullanıcı dostu ve kolay öğrenilebilir akış.
- Bol seçenek ve gelişmiş kontrol.
- Kademeli karmaşıklık; temel işlemler basit, gelişmiş seçenekler erişilebilir olacak.
- Responsive/adaptive layout.
- Tutarlı ikonografi ve durum göstergeleri.
- Canlı veriler için hafif animasyonlar.
- Tarama ve işlem durumları için açık feedback.
- Hata durumlarında açıklayıcı mesajlar ve güvenli geri dönüş.
- Gereksiz görsel kalabalıktan kaçınma.

## Aşama 6 — Network Topology

- Router merkezli dikey cihaz görünümü.
- Canlı cihaz durumu.
- Online/offline ve policy durumları.
- Cihaz sayısı arttığında okunabilirliğini koruyan yapı.
- Hafif durum geçiş animasyonları.
- Emoji kullanılmayacak.

## Aşama 7 — Device Management

- Cihaz isimlendirme.
- Cihaz türü ve metadata yönetimi.
- Cihaz detay ekranı.
- Profil bağlantısı.
- Güvenilir cihaz yönetimi.
- Cihaz geçmişi.
- Manuel düzeltme ve kimlik yönetimi.
- Yeni/kaybolan cihazlar için kullanıcıya anlaşılır bildirimler.

## Aşama 8 — Profiles + Rules

- Kullanıcı profilleri.
- `unrestricted`, `controlled`, `blocked` gibi erişim modları.
- Cihaz-profil ilişkileri.
- Gün/saat bazlı kurallar.
- Gece yarısını aşan zaman aralıkları.
- Allow/block öncelikleri.
- Kural etkin/pasif durumu.
- Profil ve kural değişiklikleri için audit eventleri.

## Aşama 9 — Gerçek Trafik Yönetimi

Birincil enforcement teknolojisi **nftables** olacak.

- NetFather'a ait ayrı nftables yapı alanı.
- Dinamik named sets.
- Gerekli yerlerde verdict maps.
- Cihaz/politika bazlı IP setleri.
- Sayaçlar.
- Güvenli apply/rollback.
- Self-lockout koruması.
- Mevcut bağlantıların policy değişikliğini atlatmaması için conntrack yönetimi.

Bant genişliği ve trafik şekillendirme için:

- Linux `tc`.
- Rate limiting.
- Gerekli olduğunda delay/policing/scheduling.

Amaç: GUI'de görünen politika ile gerçek ağ trafiğinin aynı davranışı göstermesi.

## Aşama 10 — Monitoring

- nftables counters.
- tc statistics.
- Interface counters.
- Conntrack bilgileri.
- Cihaz başına trafik istatistikleri.
- Canlı upload/download oranları mümkün olduğunda.
- Policy hit counts.
- Block/allow eventleri.
- Geçmiş olay ve trafik özeti.

Sürekli Python/Scapy packet sniffing ana telemetry yöntemi olmayacak; kernel seviyesindeki sayaçlar ve uygun Linux ağ kaynakları tercih edilecek.

## Aşama 11 — Privileged Service / D-Bus

- GUI root olarak çalışmayacak.
- Ayrıcalıklı ağ işlemleri Linux servisinde çalışacak.
- GUI ↔ servis iletişimi D-Bus üzerinden yapılacak.
- Discovery, policy, nftables ve tc işlemleri servis katmanında güvenli şekilde yürütülecek.
- Yetki sınırları açıkça tanımlanacak.

## Aşama 12 — Security, Recovery ve Reliability

- Güvenli varsayılanlar.
- Self-lockout önleme.
- Apply başarısında/başarısızlığında rollback.
- Servis çökmesi sonrası güvenli toparlanma.
- Bozuk veya eksik ağ durumunda fail-safe davranış.
- Audit logları.
- Veri bütünlüğü kontrolleri.
- Yetkisiz GUI işlemlerinin engellenmesi.

## Aşama 13 — Full Integration Testing

- Unit testler.
- Discovery testleri.
- Identity resolution testleri.
- Policy testleri.
- nftables network namespace testleri.
- Gerçek paket davranışı testleri.
- tc testleri.
- Servis/D-Bus testleri.
- GUI state ve background task testleri.
- Yeni cihaz → profil → kural → enforcement uçtan uca testleri.

## Aşama 14 — Packaging ve Release

- Linux paketleme.
- Bağımlılıkların netleştirilmesi.
- systemd entegrasyonu.
- Kurulum/kaldırma akışı.
- İlk kararlı GTK4 sürümü.
- Kullanıcı dokümantasyonu.
- Release checklist.

## Geliştirme İş Akışı

Her büyük değişiklikte:

**Mevcut çalışan durum → yedek → implementasyon → test → kullanıcı testi → sorun varsa rollback → başarılıysa yeni stabil yedek**

Ana branch gereksiz büyük ve riskli değişikliklerle yüklenmeyecek. Özellikler mantıksal ve geri alınabilir commitlerle ilerletilecek.

## Öncelikli Başlangıç

İlk büyük implementasyon:

**Application Core + Device Identity**

Bunun üzerine sırasıyla Discovery 3.0, Live Network State ve gerçek GTK4 ekranları kurulacak. Böylece GUI yalnızca görsel bir kabuk değil, NetFather'ın gerçek ağ motoruyla aynı state ve event sistemini kullanan tam bir uygulama haline gelecek.

## Nihai Hedef

NetFather; Linux üzerinde çalışan, modern ve kullanıcı dostu GTK4/Libadwaita arayüzüne sahip, yerel ağdaki cihazları güvenilir biçimde keşfedip tanımlayan, cihazları profillere bağlayan, zamanlama ve politika uygulayan, gerçek nftables/tc trafik yönetimi gerçekleştiren ve canlı ağ durumunu anlaşılır biçimde gösteren profesyonel bir açık kaynak ağ yönetimi ve ebeveyn kontrol uygulaması olacaktır.
