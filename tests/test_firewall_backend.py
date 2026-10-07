from types import SimpleNamespace

from firewall.backends import NftablesBackend


def test_existing_nftables_table_is_updated_without_recreation(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="table inet netfather { set blocked4 { type ipv4_addr; } set blocked6 { type ipv6_addr; } }", stderr="")

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
        "flush set inet netfather blocked6",
        "add element inet netfather blocked4 { 192.168.1.21, 192.168.1.22 }",
    ]
    assert scripts[1] == scripts[2]
    assert not any("delete table" in (text or "") for _, text in calls)


def test_existing_nftables_table_can_be_cleared_without_recreation(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="table inet netfather { set blocked4 { type ipv4_addr; } set blocked6 { type ipv6_addr; } }", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().apply([], apply=True)

    assert result.applied is True
    assert result.blocked_ips == ()
    scripts = [text for _, text in calls if text]
    assert scripts[0].startswith("table inet netfather_check")
    assert scripts[1:] == [
        "flush set inet netfather blocked4\n"
        "flush set inet netfather blocked6\n",
        "flush set inet netfather blocked4\n"
        "flush set inet netfather blocked6\n",
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
        "flush set inet netfather blocked4\n"
        "flush set inet netfather blocked6\n",
        "flush set inet netfather blocked4\n"
        "flush set inet netfather blocked6\n",
    ]
    assert not any("delete table" in (text or "") for _, text in calls)


def test_nftables_preview_supports_ipv4_and_ipv6() -> None:
    preview = NftablesBackend().preview(["192.168.1.21", "fd00::21"])
    assert "set blocked4 { type ipv4_addr; elements = { 192.168.1.21 } }" in preview
    assert "set blocked6 { type ipv6_addr; elements = { fd00::21 } }" in preview
    assert "ip saddr @blocked4 drop;" in preview
    assert "ip6 saddr @blocked6 drop;" in preview
    assert "ip daddr @blocked4 drop;" in preview
    assert "ip6 daddr @blocked6 drop;" in preview


def test_nftables_apply_updates_ipv4_and_ipv6_sets_atomically(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        return SimpleNamespace(returncode=0, stdout="table inet netfather { set blocked4 { type ipv4_addr; } set blocked6 { type ipv6_addr; } }", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().apply(["192.168.1.21", "fd00::21"], apply=True)

    assert result.applied is True
    assert result.blocked_ips == ("192.168.1.21", "fd00::21")
    scripts = [text for _, text in calls if text]
    assert scripts[1] == (
        "flush set inet netfather blocked4\n"
        "flush set inet netfather blocked6\n"
        "add element inet netfather blocked4 { 192.168.1.21 }\n"
        "add element inet netfather blocked6 { fd00::21 }\n"
    )
    assert scripts[1] == scripts[2]


def test_existing_legacy_table_is_upgraded_to_ipv6_without_recreation(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, input_text=None):
        calls.append((args, input_text))
        if args[1:4] == ["list", "table", "inet"]:
            return SimpleNamespace(
                returncode=0,
                stdout="table inet netfather { set blocked4 { type ipv4_addr; } }",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("firewall.backends.shutil.which", lambda name: "/usr/sbin/nft")
    monkeypatch.setattr("firewall.backends._run", fake_run)

    result = NftablesBackend().apply(["fd00::21"], apply=True)

    assert result.applied is True
    scripts = [text for _, text in calls if text]
    assert any("add set inet netfather blocked6 { type ipv6_addr; }" in text for text in scripts)
    assert any("add rule inet netfather input ip6 saddr @blocked6 drop" in text for text in scripts)
    assert any("flush set inet netfather blocked6" in text for text in scripts)
    assert not any("delete table" in (text or "") for _, text in calls)
