from __future__ import annotations
import stat
from pathlib import Path
import pytest
import core.config as config_module
from core.exceptions import ConfigError

@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "data"
    monkeypatch.setattr(config_module, "DEFAULT_DATA_DIR", fake)
    return fake

def test_load_config_creates_file_and_directories(tmp_path: Path, isolated_data_dir: Path) -> None:
    path = tmp_path / "config" / "config.toml"
    cfg = config_module.load_config(path)
    assert path.exists() and cfg.data_dir == isolated_data_dir
    assert (cfg.data_dir / "logs").is_dir()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

def test_existing_config_is_preserved(tmp_path: Path, isolated_data_dir: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f'[general]\ndata_dir = "{isolated_data_dir}"\n\n[logging]\nlevel = "DEBUG"\n', encoding="utf-8")
    assert config_module.load_config(path).logging.level == "DEBUG"

def test_invalid_values_raise(tmp_path: Path, isolated_data_dir: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[logging]\nlevel = "NOPE"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        config_module.load_config(path)

def test_derived_paths(tmp_path: Path, isolated_data_dir: Path) -> None:
    cfg = config_module.load_config(tmp_path / "config.toml")
    assert cfg.database_path == isolated_data_dir / "netfather.db"
    assert cfg.log_path == isolated_data_dir / "logs" / "netfather.log"
