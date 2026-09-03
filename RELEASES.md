# NetFather Release Guide

This document defines the v0.4+ release process and the assets expected on the GitHub **Releases** page.

## Release artifacts

The `Build and Release` workflow creates native standalone executables with PyInstaller and packages them with the README, this release guide, and the MIT license.

| Asset | Target |
|---|---|
| `NetFather-windows-x64.zip` | Windows x64 |
| `NetFather-windows-arm64.zip` | Windows ARM64 |
| `NetFather-linux-x64.tar.gz` | Linux x64 / glibc |
| `NetFather-linux-arm64.tar.gz` | Linux ARM64 / glibc |
| `NetFather-macos-x64.tar.gz` | macOS Intel |
| `NetFather-macos-arm64.tar.gz` | macOS Apple Silicon |
| `SHA256SUMS.txt` | SHA-256 hashes for all release assets |

GitHub also provides automatic source-code `.zip` and `.tar.gz` downloads for each tag.

## Workflows

### CI

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests, and manual dispatch.

Matrix:

- Windows, Linux, macOS
- Python 3.12, 3.13, 3.14
- full pytest suite
- CLI `--version`, `platform`, and `doctor` smoke tests

A release should not be created while CI is failing on `main`.

### Build and Release

`.github/workflows/release.yml` can run in two ways.

#### 1. Build artifacts without publishing a Release

Open:

`GitHub → Actions → Build and Release → Run workflow`

Set:

```text
tag: v0.4.0
publish_release: false
```

The workflow validates the version, runs the test suite, builds every OS/architecture target, and stores the archives as Actions artifacts for inspection.

Use this before tagging a release when changing packaging behavior.

#### 2. Publish from a version tag

Before tagging, the following must agree:

```text
core/version.py     VERSION = "0.4.0"
pyproject.toml      version = "0.4.0"
tag                 v0.4.0
```

Then:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.4.0 -m "NetFather v0.4.0"
git push origin v0.4.0
```

A `v*.*.*` tag automatically triggers the release workflow. It:

1. validates the tag against `core.version.VERSION`;
2. runs tests;
3. builds the six native archives;
4. verifies the runner/Python architecture and smoke-tests every executable on the runner that built it;
5. creates `SHA256SUMS.txt`;
6. creates the GitHub Release and uploads all assets.

If the Release already exists, rerunning with publish enabled replaces assets of the same name.

## Manual publish

The workflow can also publish without a tag-push event:

`Actions → Build and Release → Run workflow`

```text
tag: v0.4.0
publish_release: true
```

Use this only when the matching tag/version state is intentional. The workflow refuses a mismatched version.

## Local build

Install build dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Build the executable for the **current** operating system and architecture:

```bash
python -m PyInstaller --clean --noconfirm --onefile --name netfather netfather.py
```

PyInstaller is not a cross-compiler. A Windows executable must be built on Windows, a Linux binary on Linux, and a macOS binary on macOS. This is why the GitHub Actions workflow uses native runners for every target.

Then package the build using one of the supported target identifiers:

```bash
python scripts/package_release.py --target linux-x64
python scripts/package_release.py --target linux-arm64
python scripts/package_release.py --target windows-x64
python scripts/package_release.py --target windows-arm64
python scripts/package_release.py --target macos-x64
python scripts/package_release.py --target macos-arm64
```

## Verification checklist

Before publishing:

- [ ] `core/version.py` and `pyproject.toml` versions match.
- [ ] `CHANGELOG.md` contains the new version.
- [ ] README download commands use the stable asset names.
- [ ] CI passes on Windows/Linux/macOS.
- [ ] Release workflow validation passes.
- [ ] Every native executable passes `--version` and `platform` on its native build runner.
- [ ] `SHA256SUMS.txt` exists and contains every archive.
- [ ] Release notes clearly call out breaking/config migration changes.

## Signing and notarization

v0.4.0 establishes native builds but does not require commercial signing credentials.

Future release hardening should add:

- Windows Authenticode signing;
- Apple Developer ID signing + notarization;
- provenance/SBOM generation;
- optional package-manager publishing (WinGet, Homebrew, distro packages).

Signing credentials must be stored in GitHub Actions secrets and must never be committed to the repository.

## Linux compatibility note

PyInstaller Linux bundles are built on Ubuntu 22.04 GitHub-hosted runners to keep the glibc baseline lower than a latest-runner build. Older distributions with an older glibc, or musl-only systems such as Alpine, may still require source installation or a future dedicated musl build.

## Rollback

If a release asset is faulty:

1. mark the release as pre-release or remove the affected asset;
2. fix the issue on a branch;
3. rerun CI and build-only workflow;
4. publish a patch version such as `v0.4.1` instead of silently changing application source under an existing tag.

The workflow supports asset replacement for interrupted/retried builds, but versioned source history should remain immutable.
