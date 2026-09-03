# NetFather

[![CI](https://github.com/Praxis1071/NetFather/actions/workflows/ci.yml/badge.svg)](https://github.com/Praxis1071/NetFather/actions/workflows/ci.yml)
[![Build and Release](https://github.com/Praxis1071/NetFather/actions/workflows/release.yml/badge.svg)](https://github.com/Praxis1071/NetFather/actions/workflows/release.yml)
[![Latest Release](https://img.shields.io/github/v/release/Praxis1071/NetFather?display_name=tag&sort=semver)](https://github.com/Praxis1071/NetFather/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Praxis1071/NetFather/total)](https://github.com/Praxis1071/NetFather/releases)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555)](#platform-support)
[![License](https://img.shields.io/github/license/Praxis1071/NetFather)](LICENSE)

**NetFather** is a terminal-first local network management application for discovering devices you are authorized to manage, keeping device records, assigning profiles, and preparing time-based access policies. It provides both a Typer/Rich CLI and an interactive Rich TUI.

> NetFather is not a pentest, exploit, password-cracking, phishing, or Wi-Fi attack framework. Use it only on networks you own or are authorized to administer.

## v0.4.0

v0.4.0 turns NetFather into a multi-platform application and adds a release pipeline that produces ready-to-run builds for the major desktop operating systems.

### Highlights

- Official **Windows, Linux, and macOS** runtime support.
- Cross-platform network status and passive neighbor discovery.
- Cross-platform TUI input handling, including native Windows Console keys.
- Terminal compatibility modes: `auto`, `inline`, `fullscreen`, and `plain`.
- Platform-native config/data directories.
- `netfather platform` runtime/backend inspection.
- Platform-aware `netfather doctor` diagnostics.
- Device CRUD and discovery sync.
- Profile CRUD (`unrestricted`, `controlled`, `blocked`).
- Time-based rule CRUD and schedule evaluation, including overnight windows such as `22:00-07:00`.
- Local-only OUI/vendor lookup; device MAC addresses are not sent to a remote lookup service.
- GitHub Actions CI across Windows/Linux/macOS and Python 3.12-3.14.
- Release builds for x64/ARM64 where GitHub-hosted runners are available.
- Release checksums (`SHA256SUMS.txt`).

## Platform support

| Platform | Status | Network status backend | Passive discovery backend |
|---|---|---|---|
| Linux x64 / ARM64 | Official | `ip route get` | `ip neigh` |
| Windows x64 / ARM64 | Official | PowerShell `Get-NetIPConfiguration` | `Get-NetNeighbor`, fallback `arp -a` |
| macOS Intel / Apple Silicon | Official | `route` + `ipconfig` | `arp -an` |
| Other POSIX systems | Experimental | socket fallback | best-effort `arp` fallback |

Passive discovery reads the operating system's existing neighbor/ARP cache. It does not automatically add unknown hosts to the database.

## Download and install

The recommended installation method is the **Releases** page. Each release contains separate portable builds for each supported OS/architecture plus `SHA256SUMS.txt`.

### Windows x64

PowerShell:

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-windows-x64.zip" `
  -OutFile "NetFather-windows-x64.zip"

Expand-Archive .\NetFather-windows-x64.zip -DestinationPath . -Force
.\NetFather\netfather.exe --version
.\NetFather\netfather.exe doctor
```

### Windows ARM64

```powershell
Invoke-WebRequest `
  -Uri "https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-windows-arm64.zip" `
  -OutFile "NetFather-windows-arm64.zip"

Expand-Archive .\NetFather-windows-arm64.zip -DestinationPath . -Force
.\NetFather\netfather.exe --version
```

### Linux x64

```bash
curl -L -o NetFather-linux-x64.tar.gz \
  https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-linux-x64.tar.gz

tar -xzf NetFather-linux-x64.tar.gz
sudo install -m 0755 NetFather/netfather /usr/local/bin/netfather
netfather --version
netfather doctor
```

### Linux ARM64

```bash
curl -L -o NetFather-linux-arm64.tar.gz \
  https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-linux-arm64.tar.gz

tar -xzf NetFather-linux-arm64.tar.gz
sudo install -m 0755 NetFather/netfather /usr/local/bin/netfather
```

### macOS Apple Silicon (ARM64)

```bash
curl -L -o NetFather-macos-arm64.tar.gz \
  https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-macos-arm64.tar.gz

tar -xzf NetFather-macos-arm64.tar.gz
chmod +x NetFather/netfather
./NetFather/netfather --version
```

### macOS Intel (x64)

```bash
curl -L -o NetFather-macos-x64.tar.gz \
  https://github.com/Praxis1071/NetFather/releases/latest/download/NetFather-macos-x64.tar.gz

tar -xzf NetFather-macos-x64.tar.gz
chmod +x NetFather/netfather
./NetFather/netfather --version
```

The current macOS binaries are CI-built portable binaries and are not guaranteed to be Apple-notarized. If macOS policy blocks an unsigned build, use the Python/source installation until signed/notarized releases are introduced.

### Verify downloads

Download `SHA256SUMS.txt` from the same release.

Linux:

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

macOS:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

PowerShell:

```powershell
Get-FileHash .\NetFather-windows-x64.zip -Algorithm SHA256
```

Compare the printed hash with the corresponding entry in `SHA256SUMS.txt`.

## Install from source

Use this for development or when you want to run directly from Python:

```bash
git clone https://github.com/Praxis1071/NetFather.git
cd NetFather
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

Then:

```bash
netfather --version
netfather doctor
```

## TUI

In an interactive terminal, running NetFather without a subcommand opens the TUI:

```bash
netfather
```

Or explicitly:

```bash
netfather tui
```

Compatibility modes:

```bash
netfather tui --mode auto
netfather tui --mode inline
netfather tui --mode fullscreen
netfather tui --mode plain
```

`auto` is the recommended default and prefers the compatibility-oriented inline renderer.

### TUI keys

| Key | Action |
|---|---|
| `↑` / `↓` | Move navigation selection |
| `j` / `k` | Portable navigation fallback |
| `Home` / `End` | Jump to first/last navigation item |
| `Enter` | Open selected screen |
| `r` | Refresh; rescans on Devices/Discovery |
| `s` | Sync known registered devices from the latest discovery result |
| `q` / `Ctrl+C` | Exit |

## CLI

### Runtime and diagnostics

```bash
netfather platform
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

`--sync-known` updates only already-registered MAC addresses. Unknown hosts are not automatically persisted.

### Devices

```bash
netfather device add --name "Tablet" --mac AA:BB:CC:DD:EE:FF --type tablet
netfather device list
netfather device info "Tablet"
netfather device update "Tablet" --ip 192.168.1.25 --type tablet
netfather device remove "Tablet"
```

### Profiles

```bash
netfather profile create --device "Tablet" --name "Child" --mode controlled
netfather profile list
netfather profile set-mode 1 blocked
netfather profile remove 1
```

### Rules

```bash
netfather rules create \
  --device "Tablet" \
  --action block \
  --schedule 22:00-07:00 \
  --description "Night schedule"

netfather rules list
netfather rules active
netfather rules disable 1
netfather rules enable 1
netfather rules remove 1
```

## Data paths

NetFather uses platform-native paths by default. XDG overrides remain supported on every OS for portable/development environments.

| OS | Config | Data/database/logs |
|---|---|---|
| Linux | `~/.config/netfather/config.toml` | `~/.local/share/netfather/` |
| Windows | `%APPDATA%\NetFather\config.toml` | `%LOCALAPPDATA%\NetFather\` |
| macOS | `~/Library/Application Support/NetFather/config.toml` | `~/Library/Application Support/NetFather/` |

The exact paths in use can always be inspected with:

```bash
netfather platform
netfather config
```

## Local vendor lookup

Set a custom IEEE/Wireshark OUI file with:

```bash
export NETFATHER_OUI_FILE=/path/to/oui.txt
```

PowerShell:

```powershell
$env:NETFATHER_OUI_FILE = "C:\path\to\manuf"
```

Without a local OUI database discovery still works; only vendor names are unavailable.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The GitHub CI workflow runs the suite on Windows, Linux, and macOS using Python 3.12, 3.13, and 3.14.

## Building releases

Release binaries are built natively on GitHub-hosted runners with PyInstaller. See [RELEASES.md](RELEASES.md) for the complete release procedure and artifact names.

The release workflow produces:

```text
NetFather-windows-x64.zip
NetFather-windows-arm64.zip
NetFather-linux-x64.tar.gz
NetFather-linux-arm64.tar.gz
NetFather-macos-x64.tar.gz
NetFather-macos-arm64.tar.gz
SHA256SUMS.txt
```

## Current limitation

Rules are stored and evaluated, but privileged firewall enforcement is intentionally not enabled yet. The scheduler/firewall layer will be implemented separately so that Windows Firewall, Linux nftables, and macOS packet-filter behavior can be designed and tested independently instead of pretending one OS-specific implementation is portable.

Live packet/traffic monitoring is also planned for a later release.

## Project structure

```text
NetFather/
├── netfather.py
├── cli/                 # Typer commands and Rich output
├── tui/                 # TUI state/data/render/portable terminal input
├── core/                # config, database, platform, logging, diagnostics
├── network/             # cross-platform status/discovery/OUI lookup
├── models/              # SQLAlchemy ORM models
├── manager/             # device/profile/rule business logic
├── scheduler/           # future enforcement scheduler
├── monitor/             # future live monitoring
├── scripts/             # release/version helper scripts
├── .github/workflows/   # CI + multi-platform release builds
└── tests/
```

## Roadmap

| Area | Status |
|---|---|
| Config / DB / logging / CLI | ✅ |
| Windows/Linux/macOS platform abstraction | ✅ v0.4 |
| Cross-platform network status | ✅ v0.4 |
| Cross-platform passive discovery | ✅ v0.4 |
| Cross-platform TUI | ✅ v0.4 |
| Multi-OS CI + release builds | ✅ v0.4 |
| Device/profile/rule management | ✅ |
| Local OUI vendor lookup | ✅ |
| Signed/notarized release pipeline | ⏳ |
| OS-specific firewall enforcement | ⏳ |
| Scheduler daemon/service | ⏳ |
| Live traffic monitoring | ⏳ |
| Optional active discovery backend | ⏳ |

## License

NetFather is licensed under the [MIT License](LICENSE).
