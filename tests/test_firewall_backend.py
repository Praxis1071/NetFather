from types import SimpleNamespace

from firewall.backends import NftablesBackend


def test_existing_nftables_table_is_updated_without_recreation(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="existing table", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().apply(["192.168.1.21", "192.168.1.22"], apply=True)

    assert result.applied is True
    assert result.blocked_ips == ("192.168.1.21", "192.168.1.22")
    scripts = [text for _, text in calls if text]
    assert len(scripts) == 3
    assert "table inet netfather_check" in scripts[0]
    assert "flush set inet netfather blocked4" in scripts[1]
    assert "add element inet netfather blocked4 { 192.168.1.21, 192.168.1.22 }" in scripts[1]
    assert scripts[1].splitlines() == [
        "flush set inet netfather blocked4",
        "add element inet netfather blocked4 { 192.168.1.21, 192.168.1.22 }",
    ]
    assert scripts[1] == scripts[2]
    assert not any("delete table" in (text or "") for _, text in calls)


def test_existing_nftables_table_can_be_cleared_without_recreation(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="existing table", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().apply([], apply=True)

    assert result.applied is True
    assert result.blocked_ips == ()
    scripts = [text for _, text in calls if text]
    assert scripts[0].startswith("table inet netfather_check")
    assert scripts[1:] == [
        "flush set inet netfather blocked4\n",
        "flush set inet netfather blocked4\n",
    ]


def test_nftables_rollback_clears_set_without_deleting_table(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().rollback(apply=True)

    assert result.applied is True
    assert result.blocked_ips == ()
    scripts = [text for _, text in calls if text]
    assert scripts == [
        "flush set inet netfather blocked4\n",
        "flush set inet netfather blocked4\\n",
    ]
    assert not any("delete table" in (text or "") for _, text in calls)
