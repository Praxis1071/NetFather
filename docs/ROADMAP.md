# NetFather Development Roadmap

## Proje Vizyonu

NetFather; Linux üzerinde çalışan, kullanıcının kendi yerel ağındaki cihazları keşfetmesini, tanımlamasını, yönetmesini ve ebeveyn kontrol sistemi gibi ağ erişim politikaları uygulamasını sağlayan açık kaynaklı yerel ağ yönetim platformudur.

Nihai hedef:

- Yerel ağdaki cihazları güvenilir şekilde keşfetmek
- Cihazları isimlendirmek ve yönetmek
- Cihazları kullanıcı profillerine bağlamak
- Zaman ve politika tabanlı ağ erişim kuralları uygulamak
- Canlı ağ durumunu görsel olarak izlemek
- Linux üzerinde modern GTK4 GUI uygulaması sunmak

## Geliştirme Stratejisi

NetFather terminal/TUI ağırlıklı yapıdan modern Linux masaüstü uygulamasına dönüşecektir.

Ana hedef:

CLI/TUI -> GTK4 GUI

Ağ motorları GUI'den bağımsız geliştirilecektir.

# Aşama 1 - Proje Temizliği ve Linux Odaklama

- Gereksiz Windows/macOS odaklı yapıların kaldırılması
- Bağımlılık temizliği
- Linux ağ araçlarına odaklanma
- Modüler yapının korunması

# Aşama 2 - Network Discovery Motoru

- Scapy entegrasyonu
- ARP discovery
- ICMP/ping discovery
- Neighbor table desteği
- MAC ve vendor tespiti
- Yeni cihaz algılama
- Kaybolan cihaz algılama

# Aşama 3 - Canlı Ağ İzleme

- Arka planda sürekli network monitoring
- Online/offline cihaz takibi
- Discovery geçmişi
- Canlı olay sistemi

# Aşama 4 - GTK4 GUI Geçişi

GTK4 + Libadwaita tabanlı masaüstü uygulaması:

- Dashboard
- Network Discovery
- Devices
- Profiles
- Rules
- Monitoring
- Settings

# Aşama 5 - Network Topology Görünümü

- Profesyonel dikey cihaz listesi görünümü
- Router merkezli ağ görünümü
- Canlı cihaz durumu
- Anlaşılır grafik arayüz
- Emoji kullanılmayacak

# Aşama 6 - Cihaz Yönetimi

- Cihaz isimlendirme
- Cihaz türü belirleme
- Profil bağlantısı
- Güvenilir cihaz yönetimi

# Aşama 7 - Ebeveyn Kontrol Sistemi

- Kullanıcı profilleri
- Zamanlama sistemi
- Cihaz bazlı limitler
- Ağ erişim politikaları

# Aşama 8 - Gerçek Trafik Yönetimi

Araştırılacak teknolojiler:

- nftables
- iptables
- tc
- Linux firewall entegrasyonu

Amaç: cihazların ağ erişimini gerçek trafik seviyesinde yönetmek.

# Aşama 9 - Stabilizasyon

- Test kapsamının artırılması
- Performans iyileştirmeleri
- Hata yönetimi
- Log sistemi
- Kullanıcı deneyimi iyileştirmeleri

## Geliştirme Kuralları

- Büyük değişikliklerden önce yedek alınacak.
- Küçük ve anlamlı commitler yapılacak.
- Çalışan özellikler gereksiz yere bozulmayacak.
- Önce analiz, sonra geliştirme yapılacak.
- Ağ motorları GUI'den bağımsız tutulacak.

## Nihai Hedef

NetFather; Linux için açık kaynaklı, modern GTK4 arayüzlü, gerçek yerel ağ keşfi yapan, cihaz yönetimi sağlayan ve ebeveyn kontrol özellikleri bulunan profesyonel bir ağ yönetim uygulaması olacaktır.
