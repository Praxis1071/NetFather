# Changelog

All notable NetFather changes are documented here.

## 0.4.0 - 2026-09-03

### Added

- Official Windows, Linux, and macOS runtime support.
- Platform abstraction and platform-native config/data directories.
- Windows network status via `Get-NetIPConfiguration`.
- Windows passive discovery via `Get-NetNeighbor` with `arp -a` fallback.
- macOS network status via `route` + `ipconfig`.
- macOS passive discovery via `arp -an`.
- Windows Console TUI key input using `msvcrt`.
- TUI resize polling for platforms without `SIGWINCH`.
- `netfather platform` command.
- Platform-aware `netfather doctor` diagnostics.
- Expanded local OUI lookup paths for Wireshark/Homebrew/Windows installations.
- Cross-platform GitHub Actions CI for Python 3.12-3.14.
- Native release build matrix for Linux x64/ARM64, Windows x64/ARM64, and macOS Intel/Apple Silicon.
- PyInstaller packaging helper, release tag/version/architecture validation, and SHA-256 release checksums.
- `RELEASES.md` release/publishing guide.

### Changed

- Project metadata and documentation now describe NetFather as multi-platform.
- Discovery wording is backend-neutral rather than Linux/`ip neigh` specific.
- TUI terminal handling is no longer Linux-only.
- Default filesystem locations follow OS conventions while preserving XDG overrides.

### Fixed

- Terminal compatibility regressions across xterm/tmux/screen/SSH/minimal terminals from the v0.3 series.
- Rich terminal-size initialization with stale `COLUMNS`/`LINES` values.
- POSIX-only terminal input assumptions that prevented Windows TUI use.

## 0.3.0 - 2026-09-02

### Added

- Interactive Rich TUI with Overview, Devices, Network, Discovery, Profiles, Rules, Configuration, Logs and Monitor views.
- Device update and discovery sync support.
- Profile CRUD and time-based rule CRUD/evaluation.
- Local OUI vendor lookup.
- `netfather doctor` diagnostics command.
- TUI PTY integration tests and packaging checks.

### Changed

- Version metadata unified around the package version.
- Packaging excludes runtime cache artifacts.

## 0.2.0

- Basic network interface detection and passive `ip neigh` discovery.

## 0.1.0

- Initial config/database/logging/CLI/device-management foundation.
