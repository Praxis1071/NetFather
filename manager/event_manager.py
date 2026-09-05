"""Event and audit log management."""
from __future__ import annotations
import json
from typing import Any
from sqlalchemy import select
from core.database import Database
from models.event import Event

class EventManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, event_type: str, description: str, *, device_mac: str | None = None,
               severity: str = "info", metadata: dict[str, Any] | None = None) -> Event:
        with self.db.session() as session:
            event = Event(event_type=event_type[:32], description=description[:512],
                          device_mac=device_mac, severity=severity[:16],
                          metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None)
            session.add(event); session.flush(); session.refresh(event); session.expunge(event)
            return event

    def list_events(self, *, limit: int = 100, event_type: str | None = None) -> list[Event]:
        with self.db.session() as session:
            stmt = select(Event).order_by(Event.timestamp.desc(), Event.id.desc()).limit(max(1, min(limit, 1000)))
            if event_type:
                stmt = stmt.where(Event.event_type == event_type)
            events = list(session.scalars(stmt).all())
            for event in events: session.expunge(event)
            return events
