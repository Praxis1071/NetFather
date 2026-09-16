from core.privileges import PrivilegeMode, PrivilegeStatus, detect_privileges


def test_detect_privileges_returns_consistent_status() -> None:
    status = detect_privileges()

    assert isinstance(status.mode, PrivilegeMode)
    assert status.effective_uid >= 0
    assert status.is_root == (status.effective_uid == 0)
    assert status.can_run_privileged_operations == (status.is_root or status.pkexec_available)


def test_privilege_status_summary_prefers_root() -> None:
    status = PrivilegeStatus(
        mode=PrivilegeMode.ROOT,
        effective_uid=0,
        is_root=True,
        pkexec_available=True,
        nft_available=True,
        ip_available=True,
        network_manager_available=True,
    )

    assert status.summary == "Elevated: running as root"
