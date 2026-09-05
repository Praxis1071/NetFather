# NetFather

[![CI](https://github.com/Praxis1071/NetFather/actions/workflows/ci.yml/badge.svg)](https://github.com/Praxis1071/NetFather/actions/workflows/ci.yml)
[![Build and Release](https://github.com/Praxis1071/NetFather/actions/workflows/release.yml/badge.svg)](https://github.com/Praxis1071/NetFather/actions/workflows/release.yml)
[![Release](https://img.shields.io/github/v/release/Praxis1071/NetFather?include_prereleases)](https://github.com/Praxis1071/NetFather/releases)
[![Downloads](https://img.shields.io/github/downloads/Praxis1071/NetFather/total)](https://github.com/Praxis1071/NetFather/releases)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#platform-desteği)
[![License](https://img.shields.io/github/license/Praxis1071/NetFather)](LICENSE)

NetFather, yönettiğiniz yerel ağdaki cihazları **keşfetmek, tanımak, kalıcı olarak yönetmek, profil/policy uygulamak, zamanlamak ve gerektiğinde gerçek OS firewall backend'i ile sınırlandırmak** için geliştirilmiş Python tabanlı CLI + TUI ağ yönetim aracıdır.

> **v0.4.0** — sürüm numarası değiştirilmeden multi-platform runtime, hybrid discovery, live topology, audit/monitoring, policy engine, firewall enforcement, daemon/service ve release pipeline aynı sürüm kapsamına alınmıştır.

## v0.4.0 özellikleri

- **Hybrid discovery:** OS neighbor/ARP cache + Scapy ARP active discovery.
- **Fallback:** Scapy/Npcap/root yetkisi yoksa passive discovery çalışmaya devam eder.
- **Canlı cihaz takibi:** online/offline geçişleri grace period ile tespit edilir.
- **Otomatik kayıt:** yeni MAC ilk görüldüğünde güvenli, benzersiz isimle DB'ye alınabilir.
- **Cihaz zenginleştirme:** IP, MAC, hostname, vendor, cihaz tipi ve opsiyonel ICMP TTL tabanlı OS hint.
- **Kalıcı cihaz kimliği:** tekrar gelen cihaz MAC üzerinden tanınır; özel kullanıcı ismi korunur.
- **TUI:** Overview, Devices, Network, Discovery, Topology, Profiles, Rules, Monitoring, Events, Settings ve Logs.
- **Live topology:** gateway/router kökü + online/offline cihazlar + ALLOW/BLOCK policy durumu.
- **Profil yönetimi:** unrestricted / controlled / blocked.
- **Policy Engine:** profil ve aktif zaman kurallarından effective ALLOW/BLOCK üretir; BLOCK önceliklidir.
- **Schedule:** `HH:MM-HH:MM`, gece yarısını aşan aralıklar dahil.
- **Gerçek enforcement:** Linux nftables, Windows Defender Firewall, macOS PF.
- **Güvenli firewall scope:** yalnız NetFather table/group/anchor'ı ve yalnız private/link-local IPv4 hedefler.
- **Rollback:** NetFather kurallarını güvenli biçimde kaldırma; apply hatasında rollback denemesi.
- **Daemon:** discovery + policy + firewall sync loop.
- **Service helper:** systemd, Windows Task Scheduler, macOS LaunchDaemon plan/install/uninstall.
- **Traffic monitoring:** interface counters + Scapy ile opsiyonel gerçek packet sample ve policy sınıflandırması.
- **Event/Audit:** cihaz, profil, kural ve firewall değişiklikleri kalıcı event geçmişine yazılır.
- **Gerçek firewall testi:** Linux CI'da iki network namespace + veth + nftables + ping ile gerçek ALLOW/BLOCK doğrulaması.
- **Multi-platform releases:** Windows/Linux/macOS için x64 ve ARM64 native portable build.

## İndirme

Hazır binary kullanmak için **GitHub Releases** bölümünü tercih edin.

| OS | Mimari | Release asset |
|---|---|---|
| Windows | x64 | `NetFather-windows-x64.zip` |
| Windows | ARM64 | `NetFather-windows-arm64.zip` |
| Linux | x64 | `NetFather-linux-x64.tar.gz` |
| Linux | ARM64 | `NetFather-linux-arm64.tar.gz` |
| macOS | Intel x64 | `NetFather-macos-x64.tar.gz` |
| macOS | Apple Silicon | `NetFather-macos-arm64.tar.gz` |

Release ayrıca `SHA256SUMS.txt` içerir.

### Kaynaktan kurulum

```bash
git clone https://github.com/Praxis1071/NetFather.git
cd NetFather
python3 -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Kontrol:

```bash
netfather --version
netfather platform
netfather doctor
```

## Hızlı kullanım

### Discovery

```bash
# config'teki mode (varsayılan hybrid)
netfather scan

# yalnız OS ARP/neighbor cache
netfather scan --mode passive

# Scapy active ARP
netfather scan --mode active --subnet 192.168.1.0/24

# bulunan yeni cihazları kaydetme
netfather scan --mode hybrid --register
```

Discovery ayarlarını kalıcı değiştir:

```bash
netfather settings discovery --mode hybrid --interval 15 --auto-register
netfather settings discovery --os-detection --vendor-detection --hostname
```

### TUI ve topology

```bash
netfather
netfather tui
netfather topology
```

TUI terminal uyumluluk modları:

```bash
netfather tui --mode auto
netfather tui --mode inline
netfather tui --mode fullscreen
netfather tui --mode plain
```

### Cihaz / profil / policy

```bash
netfather device list
netfather device update "Device-ab12cd" --name "Living Room TV"
netfather profile create --device "Living Room TV" --name Family --mode controlled
netfather policy
```

### Zaman kuralı

```bash
netfather rules create \
  --device "Living Room TV" \
  --action block \
  --schedule 23:00-07:00 \
  --description "Night policy"

netfather rules active
```

### Firewall: önce preview, sonra apply

```bash
# gerçek sistem değişikliği YAPMAZ
netfather firewall sync

# yönetici/root yetkisiyle gerçek uygular
sudo netfather firewall sync --apply       # Linux/macOS
netfather firewall sync --apply            # elevated Windows terminal

# yalnız NetFather kurallarını kaldırır
netfather firewall rollback --apply
```

Firewall backend seçimi:

```bash
netfather settings firewall --backend auto
# auto => Linux:nftables, Windows:Windows Firewall, macOS:PF
```

**Varsayılan enforcement kapalıdır.** Ayrıntı: [docs/FIREWALL.md](docs/FIREWALL.md).

### Monitoring / audit

```bash
netfather monitor
netfather monitor --capture-seconds 3
netfather events --limit 100
```

Packet capture Scapy ve OS'e göre root/admin/Npcap gerektirebilir. Basic interface counters capture yetkisi olmadan çalışır.

### Daemon

Tek tur:

```bash
netfather daemon once --active-scan
netfather daemon once --apply
```

Sürekli:

```bash
netfather daemon run --interval 5
sudo netfather daemon run --apply
```

Servis planını gerçek değişiklik yapmadan gör:

```bash
netfather service plan
netfather service install
```

Gerçek kurulum:

```bash
sudo netfather service install --apply
```

Windows'ta Task Scheduler, Linux'ta systemd, macOS'ta LaunchDaemon kullanılır.

## Platform desteği

| Özellik | Linux | Windows | macOS |
|---|---:|---:|---:|
| CLI/TUI | ✅ | ✅ | ✅ |
| Passive discovery | `ip neigh` | Get-NetNeighbor / `arp -a` | `arp -an` |
| Active discovery | Scapy ARP | Scapy + Npcap | Scapy/BPF |
| Firewall | nftables | Defender Firewall | PF |
| Daemon helper | systemd | Task Scheduler | LaunchDaemon |
| x64 release | ✅ | ✅ | ✅ |
| ARM64 release | ✅ | ✅ | ✅ |

## Güvenlik modeli

NetFather yalnız **sahibi olduğunuz veya yönetme yetkinizin bulunduğu yerel ağlarda** kullanılmalıdır. Aktif discovery ve firewall işlemleri ayrıcalıklı yetki gerektirebilir.

Önemli ilkeler:

1. Firewall varsayılan olarak dry-run/enforcement disabled.
2. Gerçek uygulama açık `--apply` gerektirir.
3. Yalnız private/link-local IPv4 policy hedeflenir.
4. NetFather başka uygulamaların firewall kurallarını global olarak flush etmez.
5. nftables yalnız `inet netfather`, Windows yalnız `NetFather` group, PF yalnız `com.apple/netfather` anchor kullanır.
6. Event/audit geçmişi cihaz ve policy değişikliklerini izler.
7. OS tahmini bir **hint**tir; güvenlik kararı için kesin fingerprint değildir.

Bkz. [SECURITY.md](SECURITY.md) ve [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Config

Platform-native config/data yolları kullanılır. `netfather config --path` aktif dosyayı gösterir.

Başlıca discovery alanları:

```toml
[discovery]
mode = "hybrid"
interval_seconds = 15
active_timeout_seconds = 2
subnet = ""
auto_register = true
hostname_resolution = true
vendor_detection = true
os_detection = false
offline_after_seconds = 45

[firewall]
backend = "auto"
enforcement_enabled = false
rollback_on_error = true
```

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI ayrıca Linux'ta privileged network namespace entegrasyon testi çalıştırır.

## Mimari

```text
CLI / TUI
   │
   ├── Discovery ── passive OS cache + active Scapy
   │       │
   │       └── DeviceTracker ── Device DB + Event/Audit
   │
   ├── Profiles + Rules ── PolicyEngine
   │                         │
   │                         └── FirewallEngine
   │                              ├── nftables
   │                              ├── Windows Firewall
   │                              └── macOS PF
   │
   ├── Topology / Monitor / Events
   │
   └── RuleScheduler / Daemon / Service helper
```

## v1.0 hedef zinciri

v0.4.0 artık temel uçtan uca hattı kurar:

**Keşfet → Tanı → Topology'de göster → İsimlendir → Profile bağla → Policy hesapla → Zamanla → Firewall'a uygula → Canlı izle → Audit et**.

v1.0'a kadar hedef; backend dayanıklılığını, per-device trafik muhasebesini, servis lifecycle'ını ve platform-specific enforcement test kapsamını production seviyesine taşımaktır.

## Dokümantasyon

- [RELEASES.md](RELEASES.md) — release/build süreci
- [CHANGELOG.md](CHANGELOG.md) — sürüm değişiklikleri
- [SECURITY.md](SECURITY.md) — güvenlik ve yetki modeli
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — bileşenler/veri akışı
- [docs/DISCOVERY.md](docs/DISCOVERY.md) — active/passive discovery
- [docs/FIREWALL.md](docs/FIREWALL.md) — enforcement/rollback

## License

MIT — [LICENSE](LICENSE)
