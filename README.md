# NetFather

NetFather, kendi yönettiğiniz yerel ağdaki cihazları keşfetmek, kayıt altına almak,
isimlendirmek ve cihaz bazlı erişim politikalarını hazırlamak için geliştirilmiş
Linux terminal uygulamasıdır. Proje hem klasik **Typer + Rich CLI** hem de tam ekran
**Rich TUI** sunar.

> NetFather bir pentest/exploit aracı değildir. Yalnızca yönetme yetkinizin olduğu
> ev, lab veya küçük ofis ağlarında kullanılmak üzere tasarlanmıştır.

Hedef platform: Linux; özellikle Arch Linux / CachyOS. Python 3.12+ gerekir.

## Sürüm: 0.3.0

Bu sürüm, v0.2.0 discovery tabanını genişletir ve ilk kullanılabilir TUI ile
profil/kural yönetimini ekler.

### Öne çıkanlar

- Tam ekran terminal arayüzü (`netfather` veya `netfather tui`)
  - Overview
  - kayıtlı cihazlar
  - network status
  - discovery sonuçları
  - profiles
  - rules
  - configuration
  - logs
  - terminal resize desteği
  - `r` ile refresh/scan, `s` ile son discovery sonucundan yalnız kayıtlı
    cihazları sync etme
- `ip route get` ile interface/IP/gateway tespiti
- `ip neigh` ile temel, pasif-komşu tablosu tabanlı discovery
- Yerel OUI dosyalarından vendor lookup; MAC adresi uzak servise gönderilmez
- Cihaz CRUD + `device update`
- Discovery sonucundan kayıtlı cihazların IP/vendor/last_seen bilgisini güncelleme
  (`scan --sync-known`)
- Profil CRUD
  - `unrestricted`
  - `controlled`
  - `blocked`
- Zaman bazlı kural CRUD ve schedule değerlendirmesi
  - `allow` / `block`
  - `HH:MM-HH:MM`
  - gece yarısını aşan aralıklar desteklenir (`22:00-07:00`)
  - enable/disable ve `rules active`
- `netfather doctor` ile platform, `ip` komutu, route, config, database ve OUI
  kontrolleri
- XDG Base Directory uyumlu config/data/log yapısı
- SQLite + SQLAlchemy
- Rotating file logging
- Testlerde gerçek PTY üzerinden TUI render/çıkış regresyon kontrolleri

### Bilinen sınır

Kurallar şu anda **saklanır ve aktif/pasif olarak değerlendirilir**, ancak Linux
firewall/nftables üzerinde otomatik enforcement henüz yapılmaz. Canlı trafik
monitoring de sonraki faz içindir. Bu ayrım bilinçlidir: veri modeli ve schedule
motoru, ayrıcalıklı sistem değişikliklerinden bağımsız tutulur.

## Kurulum

```bash
git clone https://github.com/Praxis1071/NetFather.git
cd NetFather
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Kontrol:

```bash
netfather --version
netfather doctor
pytest
```

## TUI

İnteraktif terminalde alt komut vermeden çalıştırmak TUI'yi açar:

```bash
netfather
```

Açıkça çağırmak için:

```bash
netfather tui
```

Kısayollar:

| Tuş | İşlem |
|---|---|
| `↑` / `↓` | Navigation seçimini değiştir |
| `Enter` | Seçili ekranı aç |
| `r` | Refresh; Devices/Discovery ekranında yeniden scan |
| `s` | Son discovery sonucuyla yalnız kayıtlı cihazları sync et |
| `q` / `Ctrl+C` | TUI'den çık |

## CLI örnekleri

### Durum ve tanılama

```bash
netfather status
netfather doctor
netfather config
netfather config --path
```

### Discovery

```bash
netfather scan
netfather scan --sync-known
```

`--sync-known` bilinmeyen hostları otomatik eklemez. Yalnız daha önce kayıtlı
MAC adreslerinin `ip`, `vendor` ve `last_seen` alanlarını günceller.

### Cihazlar

```bash
netfather device add \
  --name "Tablet" \
  --mac AA:BB:CC:DD:EE:FF \
  --type tablet

netfather device list
netfather device info "Tablet"

netfather device update "Tablet" \
  --name "Living Room Tablet" \
  --ip 192.168.1.25 \
  --type tablet

netfather device remove "Living Room Tablet"
```

### Profiller

```bash
netfather profile create \
  --device "Living Room Tablet" \
  --name "Child" \
  --mode controlled

netfather profile list
netfather profile set-mode 1 blocked
netfather profile remove 1
```

### Kurallar

```bash
netfather rules create \
  --device "Living Room Tablet" \
  --action block \
  --schedule 22:00-07:00 \
  --description "Night schedule"

netfather rules list
netfather rules active
netfather rules disable 1
netfather rules enable 1
netfather rules remove 1
```

## Yerel vendor lookup

NetFather aşağıdaki gibi yerel OUI veritabanlarını otomatik arar:

- `/usr/share/ieee-data/oui.txt`
- `/usr/share/hwdata/oui.txt`
- `/usr/share/misc/oui.txt`
- `/var/lib/ieee-data/oui.txt`
- `/usr/share/wireshark/manuf`

Özel bir dosya kullanmak için:

```bash
export NETFATHER_OUI_FILE=/path/to/oui.txt
```

OUI dosyası yoksa discovery çalışmaya devam eder; yalnız vendor alanı boş kalır.

## Veri yolları

Varsayılanlar:

```text
~/.config/netfather/config.toml
~/.local/share/netfather/netfather.db
~/.local/share/netfather/logs/netfather.log
```

Config/data dizinleri kullanıcıya özel izinlerle oluşturulur. Log dosyası MAC/IP
gibi ağ bilgileri içerebildiği için `0600` izni uygulanmaya çalışılır.

## Proje yapısı

```text
NetFather/
├── netfather.py
├── cli/          # Typer komutları / Rich çıktı
├── tui/          # state + data aggregation + Rich renderer + terminal loop
├── core/         # config, database, logging, diagnostics, common helpers
├── network/      # interface detection, discovery, OUI lookup
├── models/       # SQLAlchemy ORM modelleri
├── manager/      # device/profile/rule iş mantığı
├── scheduler/    # gelecekteki enforcement scheduler katmanı
├── monitor/      # gelecekteki canlı monitoring katmanı
└── tests/
```

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

Test paketi manager/network/state/render davranışlarının yanında gerçek Linux PTY
üzerinden TUI'nin ilk frame'ini ve `q` ile temiz kapanmasını da doğrular.

## Yol haritası

| Alan | Durum |
|---|---|
| Temel config / DB / logging / CLI | ✅ |
| Interface + route detection | ✅ |
| `ip neigh` basic discovery | ✅ |
| TUI dashboard/navigation | ✅ |
| Device update + discovery sync | ✅ |
| Local OUI vendor lookup | ✅ |
| Profile CRUD | ✅ |
| Rule CRUD + schedule evaluation | ✅ |
| Privileged firewall/nftables enforcement | ⏳ |
| Scheduler daemon/service | ⏳ |
| Canlı traffic/device monitoring | ⏳ |
| Gelişmiş aktif discovery backend | ⏳ |

## Kapsam dışı

NetFather exploit, CVE tarama, parola kırma, phishing, Wi-Fi saldırısı veya başka
bir saldırı/pentest framework'üne dönüşmeyi hedeflemez.

## License

This project is licensed under the terms of the MIT License. See the LICENSE file for full details.
