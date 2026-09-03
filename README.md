# NetFather

NetFather, kendi yönettiğiniz yerel ağdaki (ev veya küçük ofis) cihazları
tanımlamanızı, isimlendirmenizi ve cihaz bazlı internet erişim politikaları
(zaman bazlı kısıtlamalar dahil) tanımlamanızı sağlayan, tamamen terminal
üzerinden çalışan bir Linux ağ yönetim aracıdır.

> NetFather bir pentest aracı, exploit framework'ü veya saldırı aracı
> **değildir**. Yalnızca kendi yetkili olduğunuz ağlarda kullanılmak üzere
> tasarlanmıştır.

Hedef sistemler: CachyOS, Arch Linux tabanlı dağıtımlar ve genel olarak Linux.

## Durum: FAZ 1 — Temel Altyapı

Bu sürümde şunlar mevcuttur:

- Typer + Rich tabanlı CLI iskeleti
- TOML tabanlı config sistemi (`~/.config/netfather/config.toml`)
- SQLAlchemy + SQLite database katmanı
- Rotating file logging (`~/.local/share/netfather/logs/netfather.log`)
- Temel ORM modelleri: `Device`, `Profile`, `Rule`, `Event`
- Tam işlevsel cihaz yönetimi: `device add / list / info / remove` (isim/MAC
  benzersizliği, MAC format doğrulama, silmeden önce onay)
- `status`, `config` ve `--version` komutları
- XDG Base Directory uyumlu config/veri dizinleri, güvenli (0700/0600) dosya
  izinleri
- `tests/` altında pytest tabanlı otomatik testler

`scan`, `monitor` ve `rules` komutları bu fazda **yer tutucu**dur; ilgili
işlevsellik sırasıyla FAZ 3, FAZ 6 ve FAZ 5'te eklenecektir.

## Kurulum

```bash
cd NetFather
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Geliştirme modunda kurup `netfather` komutunu doğrudan kullanmak isterseniz:

```bash
pip install -e .
netfather --help
```

Kurulum yapmadan doğrudan da çalıştırılabilir:

```bash
python netfather.py --help
```

### Geliştirme bağımlılıkları ve testler

```bash
pip install -r requirements-dev.txt
pytest
```

Testler `tests/` altındadır ve gerçek config/veri dizinlerine dokunmadan,
her biri kendi geçici (temp) dizininde izole şekilde çalışır.

## Kullanım (FAZ 1)

```bash
netfather --help
netfather status
netfather config
netfather config --path

netfather device add --name "Çocuğun Tableti" --mac AA:BB:CC:DD:EE:FF --type tablet
netfather device list
netfather device info "Çocuğun Tableti"
netfather device remove "Çocuğun Tableti"
```

## Proje Yapısı

```
NetFather/
├── netfather.py          # Giriş noktası
├── core/                 # Config, database, logging, exceptions
├── cli/                  # Typer komutları ve çıktı yardımcıları
├── network/               # Ağ arayüzü / keşif (FAZ 2-3)
├── models/                # SQLAlchemy ORM modelleri
├── manager/               # Device / Profile / Rule iş mantığı
├── monitor/                # Canlı terminal görünümü (FAZ 6)
├── scheduler/              # Zaman bazlı kural motoru (FAZ 5)
├── data/                   # Yerel veri (git'e eklenmez)
└── logs/                   # Log dosyaları (git'e eklenmez)
```

## Geliştirme Yol Haritası

| Faz | İçerik | Durum |
|-----|--------|-------|
| 1 | Temel altyapı (CLI, config, DB, logging) | ✅ Tamamlandı |
| 2 | Ağ arayüzü tespiti (interface, IP, gateway) | ⏳ Sırada |
| 3 | Yerel ağ cihaz keşfi (ARP tarama, vendor lookup) | ⏳ Planlandı |
| 4 | Profil sistemi | ⏳ Planlandı |
| 5 | Zaman bazlı kural motoru (scheduler) | ⏳ Planlandı |
| 6 | Canlı monitoring ekranı | ⏳ Planlandı |

## Kapsam Dışı

NetFather'a kesinlikle eklenmeyecekler: exploit sistemleri, CVE tarama,
parola kırma, phishing, saldırı modülleri, WiFi saldırıları veya herhangi
bir pentest özelliği.

## License

This project is licensed under the terms of the **GNU Lesser General Public License v3.0 (LGPL-3.0)**. 
See the [LICENSE](LICENSE) file for full details.
