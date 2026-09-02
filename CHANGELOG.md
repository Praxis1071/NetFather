# Changelog

## 0.3.0

- Added full-screen Rich TUI with resize-safe rendering and real PTY regression tests.
- Added Profiles CRUD and internet-mode validation.
- Added Rules CRUD, enable/disable, active-rule queries, schedule validation, and overnight windows.
- Added `device update`.
- Added `scan --sync-known` and equivalent explicit TUI sync action.
- Added privacy-preserving local OUI vendor lookup.
- Added `netfather doctor` diagnostics.
- Fixed package/version drift between Git tags, source metadata, and CLI fallback version.
- Replaced deprecated `datetime.utcnow()` usage while preserving SQLite's existing naive-UTC storage contract.
- Hardened TUI rendering against terminal-size environment drift and invalid legacy rule rows.
- Updated dependency ranges and documentation for the current feature set.

## 0.2.0

- Added basic `ip neigh` network discovery.
- Added network interface / route detection foundation.

## 0.1.0

- Initial config, SQLite/SQLAlchemy, logging, CLI, models, and device CRUD baseline.
