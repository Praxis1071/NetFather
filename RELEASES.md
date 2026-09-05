# NetFather Release Guide

## v0.4.0 release assets

Release workflow aşağıdaki native paketleri üretir:

- `NetFather-windows-x64.zip`
- `NetFather-windows-arm64.zip`
- `NetFather-linux-x64.tar.gz`
- `NetFather-linux-arm64.tar.gz`
- `NetFather-macos-x64.tar.gz`
- `NetFather-macos-arm64.tar.gz`
- `SHA256SUMS.txt`

## Release öncesi zorunlu kontrol

```bash
python -m pytest -q
python -m compileall -q .
python scripts/check_version.py --tag v0.4.0
python netfather.py --version
python netfather.py platform
python netfather.py doctor
```

Linux privileged integration CI job'ı ayrıca gerçek network namespace + nftables testini geçmelidir.

## GitHub Actions

### CI
`.github/workflows/ci.yml`:
- Windows/Linux/macOS
- Python 3.12/3.13/3.14
- normal test + CLI smoke
- Ubuntu 22.04 üzerinde isolated nftables integration job

### Build and Release
`.github/workflows/release.yml`:
- her OS/mimari kendi native runner'ında build olur
- architecture check
- target-native pytest
- PyInstaller onefile
- native binary `--version` + `platform` smoke
- package + artifact upload
- tag push'ta GitHub Release + SHA256SUMS

## v0.4.0 yayınlama

Önce `main` yeşil olmalıdır. Sonra:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.4.0 -m "NetFather v0.4.0"
git push origin v0.4.0
```

Eğer aynı tag daha önce yanlış commit'e gönderildiyse körlemesine force etmeyin. Önce GitHub Release/tag durumunu kontrol edin; gerekiyorsa owner ile koordineli düzeltin.

## Manual build-only

Actions → **Build and Release** → Run workflow:
- tag: `v0.4.0`
- `publish_release=false`

Bu mod Release yaratmadan altı native artifact üretir.

## Güvenlik release checklist

- Firewall default enforcement `false`.
- `firewall sync` dry-run; gerçek değişiklik için `--apply`.
- Linux backend global nftables ruleset'i flush etmemeli.
- Windows yalnız `NetFather` group'una dokunmalı.
- macOS yalnız `com.apple/netfather` anchor'ına dokunmalı.
- Active discovery local/bounded subnet dışında tarama yapmamalı.
- Yeni DB migration eski v0.x database üzerinde veri silmemeli.
