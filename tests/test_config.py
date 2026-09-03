"""core.config için testler: dosya/dizin oluşturma, izinler ve doğrulama."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import core.config as config_module
from core.exceptions import ConfigError


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DEFAULT_DATA_DIR'ı gerçek ev dizini yerine geçici bir dizine yönlendirir."""
    fake_data_dir = tmp_path / "data"
    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", fake_data_dir)
    return fake_data_dir


def test_load_config_creates_file_when_missing(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config" / "config.toml"
    assert not config_path.exists()

    cfg = config_module.load_config(config_path=config_path)

    assert config_path.exists()
    assert cfg.config_path == config_path
    assert cfg.database.filename == "netfather.db"


def test_load_config_creates_data_and_log_directories(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"

    cfg = config_module.load_config(config_path=config_path)

    assert cfg.data_dir == isolated_data_dir
    assert cfg.data_dir.is_dir()
    assert (cfg.data_dir / "logs").is_dir()


@pytest.mark.skipif(os.name == "nt", reason="Windows uses ACLs rather than POSIX chmod bits")
def test_created_directories_have_secure_permissions(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"

    cfg = config_module.load_config(config_path=config_path)

    for path in (cfg.config_path.parent, cfg.data_dir, cfg.data_dir / "logs"):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o700, f"{path} beklenmedik izinde: {oct(mode)}"


def test_derived_paths_are_computed_correctly(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"

    cfg = config_module.load_config(config_path=config_path)

    assert cfg.database_path == isolated_data_dir / "netfather.db"
    assert cfg.log_path == isolated_data_dir / "logs" / "netfather.log"


def test_existing_config_file_is_not_overwritten(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # [general] bilinçli olarak isolated_data_dir'e işaret edecek şekilde
    # yazılır; aksi halde GeneralConfig'in dataclass varsayılanı (gerçek ev
    # dizini) kullanılır ve test gerçek dosya sistemine dokunabilir.
    config_path.write_text(
        f'[general]\ndata_dir = {json.dumps(str(isolated_data_dir))}\n\n'
        '[logging]\nlevel = "DEBUG"\n',
        encoding="utf-8",
    )

    cfg = config_module.load_config(config_path=config_path)

    # Dosya üzerine yazılmadı: bizim yazdığımız DEBUG seviyesi korunuyor,
    # varsayılan (INFO) ile değiştirilmedi.
    assert cfg.logging.level == "DEBUG"
    assert cfg.data_dir == isolated_data_dir


def test_invalid_log_level_raises_config_error(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[logging]\nlevel = "NOT_A_LEVEL"\n', encoding="utf-8")

    with pytest.raises(ConfigError):
        config_module.load_config(config_path=config_path)


def test_invalid_toml_raises_config_error(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("bu = geçerli [ olmayan toml", encoding="utf-8")

    with pytest.raises(ConfigError):
        config_module.load_config(config_path=config_path)


def test_negative_scan_timeout_raises_config_error(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[network]\nscan_timeout_seconds = -1\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError):
        config_module.load_config(config_path=config_path)


def test_default_config_escapes_windows_style_data_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows_style = Path(r"C:\Users\Test User\AppData\Local\NetFather")
    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", windows_style)
    config_path = tmp_path / "windows-config.toml"

    cfg = config_module.load_config(config_path=config_path)

    assert cfg.data_dir == windows_style
    # A second parse verifies the generated TOML is syntactically valid.
    cfg2 = config_module.load_config(config_path=config_path)
    assert cfg2.data_dir == windows_style
