"""Stable device identity resolution from network observations.

IP addresses are treated as mutable observations, never as the identity of a
physical/logical device. The resolver currently uses MAC as its strongest
local-network identity key and keeps a confidence score for future discovery
sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from core.time_utils import utc_now


@dataclass(frozen=True, slots=True)
class DeviceObservation:
    """A single observation produced by any discovery source."""

    mac: str
    ip: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    interface: str | None = None
    device_type: str | None = None
    os_hint: str | None = None
    source: str = "unknown"
    confidence: float = 0.0
    observed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        mac = self.mac.strip().upper().replace("-", ":")
        if not mac:
            raise ValueError("MAC adresi boş olamaz.")
        object.__setattr__(self, "mac", mac)
        confidence = max(0.0, min(1.0, float(self.confidence)))
        object.__setattr__(self, "confidence", confidence)


@dataclass(slots=True)
class DeviceIdentity:
    """Aggregated identity independent from the device's current IP."""

    mac: str
    ips: set[str] = field(default_factory=set)
    hostnames: set[str] = field(default_factory=set)
    vendors: set[str] = field(default_factory=set)
    interfaces: set[str] = field(default_factory=set)
    device_types: set[str] = field(default_factory=set)
    os_hints: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    first_seen: datetime = field(default_factory=utc_now)
    last_seen: datetime = field(default_factory=utc_now)
    online: bool = True
    confidence: float = 0.0

    @property
    def current_ip(self) -> str | None:
        return next(iter(self.ips), None)

    def observe(self, observation: DeviceObservation) -> None:
        if observation.mac != self.mac:
            raise ValueError("Observation MAC kimlik MAC'i ile eşleşmiyor.")
        self.ips.update(filter(None, (observation.ip,)))
        self.hostnames.update(filter(None, (observation.hostname,)))
        self.vendors.update(filter(None, (observation.vendor,)))
        self.interfaces.update(filter(None, (observation.interface,)))
        self.device_types.update(filter(None, (observation.device_type,)))
        self.os_hints.update(filter(None, (observation.os_hint,)))
        self.sources.add(observation.source)
        self.last_seen = observation.observed_at
        self.online = True
        self.confidence = max(self.confidence, observation.confidence)


class IdentityResolver:
    """In-memory identity aggregator for discovery and live-state services."""

    def __init__(self) -> None:
        self._identities: dict[str, DeviceIdentity] = {}

    def observe(self, observation: DeviceObservation) -> DeviceIdentity:
        identity = self._identities.get(observation.mac)
        if identity is None:
            identity = DeviceIdentity(
                mac=observation.mac,
                first_seen=observation.observed_at,
                last_seen=observation.observed_at,
                confidence=observation.confidence,
            )
            self._identities[observation.mac] = identity
        identity.observe(observation)
        return identity

    def mark_offline(self, mac: str, *, seen_before: datetime | None = None) -> None:
        identity = self._identities.get(mac.strip().upper().replace("-", ":"))
        if identity is None:
            return
        if seen_before is None or identity.last_seen <= seen_before:
            identity.online = False

    def get(self, mac: str) -> DeviceIdentity | None:
        return self._identities.get(mac.strip().upper().replace("-", ":"))

    def all(self) -> tuple[DeviceIdentity, ...]:
        return tuple(self._identities.values())

    def reconcile(self, observations: Iterable[DeviceObservation]) -> tuple[DeviceIdentity, ...]:
        observed_macs: set[str] = set()
        for observation in observations:
            self.observe(observation)
            observed_macs.add(observation.mac)
        for identity in self._identities.values():
            if identity.mac not in observed_macs:
                identity.online = False
        return self.all()
