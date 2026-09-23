from pathlib import Path

from core.config import Config
from core.database import Database
from core.diagnostics import run_diagnostics


def test_linux_diagnostics_import_and_execute(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config = Config(general=__import__("core.config", fromlist=["GeneralConfig"]).GeneralConfig(data_dir=str(data_dir)), config_path=config_path)
    db = Database(tmp_path / "netfather.db")
    db.init_db()

    checks = run_diagnostics(config, db)

    names = {check.name for check in checks}
    assert {"Platform", "Python", "Network backend", "Config", "Database"} <= names
    assert all(check.detail for check in checks)

    db.close()
