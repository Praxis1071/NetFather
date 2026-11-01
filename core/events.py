"""Committed domain events shared by backend services and UI adapters.

Delivery happens on the publishing thread. GTK consumers must provide their
main-context dispatcher. Subscribers are isolated and may safely unsubscribe.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable

from core.logger import get_logger

log = get_logger("events")


class EventType(StrEnum):
    DEVICE_DISCOVERED = "device_discovered"
    DEVICE_ONLINE = "device_online"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_UPDATED = "device_updated"
    DEVICE_DELETED = "device_deleted"
    DEVICE_IP_CHANGED = "device_ip_changed"
    IDENTITY_CONFLICT = "identity_conflict"
    IDENTITY_RESOLVED = "identity_resolved"
    IDENTITY_MERGED = "identity_merged"
    IDENTITY_SPLIT = "identity_split"
    PROFILE_CREATED = "profile_created"
    PROFILE_CHANGED = "profile_changed"
    PROFILE_DELETED = "profile_deleted"
    RULE_CREATED = "rule_created"
    RULE_CHANGED = "rule_changed"
    RULE_DELETED = "rule_deleted"
    DISCOVERY_COMPLETED = "discovery_completed"
    DISCOVERY_CANCELLED = "discovery_cancelled"
    NETWORK_CHANGED = "network_changed"
    FIREWALL_SYNC = "firewall_sync"
    FIREWALL_DRIFT = "firewall_drift"
    FIREWALL_RECOVERY_ERROR = "firewall_recovery_error"
    FIREWALL_ROLLBACK = "firewall_rollback"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    id: int
    event_type: str
    description: str
    timestamp: datetime
    device_mac: str | None = None
    severity: str = "info"
    metadata_json: str | None = None


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: dict[object, tuple[Callable, frozenset[str], Callable | None]] = {}

    def subscribe(self, callback: Callable[[DomainEvent], None], *,
                  event_types: tuple[str, ...] = (), dispatcher: Callable | None = None) -> Callable[[], None]:
        key = object()
        with self._lock:
            self._listeners[key] = (callback, frozenset(event_types), dispatcher)

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.pop(key, None)
        return unsubscribe

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            listeners = tuple(self._listeners.items())
        for key, (callback, types, dispatcher) in listeners:
            if types and event.event_type not in types:
                continue

            def deliver(key=key, callback=callback) -> None:
                with self._lock:
                    if key not in self._listeners:
                        return
                try:
                    callback(event)
                except Exception:
                    log.exception("Domain event subscriber failed")
            try:
                dispatcher(deliver) if dispatcher else deliver()
            except Exception:
                log.exception("Domain event dispatch failed")
