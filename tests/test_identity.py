from datetime import datetime, timezone

from network.identity import DeviceObservation, IdentityResolver


def test_identity_survives_ip_change() -> None:
    resolver = IdentityResolver()
    observed_at = datetime(2026, 9, 16, 10, tzinfo=timezone.utc)
    first = resolver.observe(
        DeviceObservation(
            mac="aa:bb:cc:dd:ee:ff",
            ip="192.168.1.20",
            hostname="phone",
            source="arp",
            confidence=0.8,
            observed_at=observed_at,
        )
    )
    second = resolver.observe(
        DeviceObservation(
            mac="AA-BB-CC-DD-EE-FF",
            ip="192.168.1.42",
            hostname="phone",
            source="neighbor",
            confidence=0.9,
            observed_at=observed_at.replace(minute=1),
        )
    )

    assert first is second
    assert second.mac == "AA:BB:CC:DD:EE:FF"
    assert second.current_ip == "192.168.1.42"
    assert second.ips == {"192.168.1.20", "192.168.1.42"}
    assert second.previous_ips == ("192.168.1.20",)
    assert second.online is True
    assert second.confidence == 0.9


def test_reconcile_marks_missing_devices_offline() -> None:
    resolver = IdentityResolver()
    observed_at = datetime(2026, 9, 16, tzinfo=timezone.utc)
    resolver.observe(
        DeviceObservation(
            mac="00:11:22:33:44:55",
            ip="192.168.1.10",
            source="arp",
            observed_at=observed_at,
        )
    )
    resolver.observe(
        DeviceObservation(
            mac="00:11:22:33:44:66",
            ip="192.168.1.11",
            source="arp",
            observed_at=observed_at,
        )
    )

    identities = resolver.reconcile(
        [
            DeviceObservation(
                mac="00:11:22:33:44:66",
                ip="192.168.1.11",
                source="neighbor",
                observed_at=observed_at.replace(minute=1),
            )
        ]
    )

    assert len(identities) == 2
    assert resolver.get("00:11:22:33:44:55").online is False
    assert resolver.get("00:11:22:33:44:66").online is True


def test_confidence_is_clamped_and_source_is_normalized() -> None:
    observation = DeviceObservation(
        mac="00:11:22:33:44:55",
        source="  ARP  ",
        confidence=3.5,
    )

    assert observation.source == "arp"
    assert observation.confidence == 1.0
