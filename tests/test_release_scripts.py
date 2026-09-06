from scripts.check_architecture import normalize_machine
from scripts.package_release import TARGETS


def test_release_architecture_aliases_are_normalized() -> None:
    assert normalize_machine("x86_64") == "x64"
    assert normalize_machine("AMD64") == "x64"
    assert normalize_machine("aarch64") == "arm64"
    assert normalize_machine("ARM64") == "arm64"


def test_release_matrix_is_linux_only() -> None:
    assert set(TARGETS) == {"linux-x64", "linux-arm64"}
    archive_names = [archive for _binary, archive in TARGETS.values()]
    assert len(archive_names) == len(set(archive_names)) == 2
    assert all(name.startswith("NetFather-linux-") for name in archive_names)
