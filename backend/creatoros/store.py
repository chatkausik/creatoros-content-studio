"""Small transactional SQLite document store with appendable decision events.

Versioned domain objects remain explicit JSON. This keeps the local prototype
easy to inspect/export while SQLAlchemy owns connections and transactions.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine, event, select


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "assets").mkdir(exist_ok=True)
        self.lock = RLock()
        self.engine = create_engine(
            f"sqlite:///{self.data_dir / 'studio.sqlite'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def pragmas(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        meta = MetaData()
        self.docs = Table(
            "documents", meta,
            Column("collection", String, primary_key=True),
            Column("id", String, primary_key=True),
            Column("data", JSON, nullable=False),
        )
        meta.create_all(self.engine)

    def get(self, collection: str, identifier: str) -> dict | None:
        with self.lock, self.engine.connect() as conn:
            row = conn.execute(select(self.docs.c.data).where(
                self.docs.c.collection == collection, self.docs.c.id == identifier
            )).first()
            return deepcopy(row[0]) if row else None

    def list(self, collection: str, **filters) -> list[dict]:
        with self.lock, self.engine.connect() as conn:
            rows = conn.execute(select(self.docs.c.data).where(
                self.docs.c.collection == collection
            )).all()
            return [deepcopy(row[0]) for row in rows
                    if all(row[0].get(k) == v for k, v in filters.items())]

    def put(self, collection: str, obj: dict) -> dict:
        from sqlalchemy.dialects.sqlite import insert
        value = deepcopy(obj)
        if not value.get("id"):
            raise ValueError("Stored records require an id.")
        with self.lock, self.engine.begin() as conn:
            query = insert(self.docs).values(collection=collection, id=value["id"], data=value)
            conn.execute(query.on_conflict_do_update(
                index_elements=["collection", "id"], set_={"data": value}
            ))
        return deepcopy(value)

    def patch(self, collection: str, identifier: str, changes: dict) -> dict:
        with self.lock:
            value = self.get(collection, identifier)
            if value is None:
                raise KeyError(f"{collection} record not found")
            value.update(deepcopy(changes))
            value["id"] = identifier
            return self.put(collection, value)

    def put_many(self, records: list[tuple[str, dict]]) -> None:
        """Commit a validated import and its revisions/events as one SQLite transaction."""
        from sqlalchemy.dialects.sqlite import insert
        values = [(collection, deepcopy(obj)) for collection, obj in records]
        if any(not obj.get("id") for _, obj in values):
            raise ValueError("Stored records require an id.")
        with self.lock, self.engine.begin() as conn:
            for collection, obj in values:
                query = insert(self.docs).values(collection=collection, id=obj["id"], data=obj)
                conn.execute(query.on_conflict_do_update(
                    index_elements=["collection", "id"], set_={"data": obj}
                ))

    def add_event(self, post_id: str, node: str, choice: str, reason: str,
                  evidence_ids: list | None = None, event_id: str | None = None) -> dict:
        identifier = event_id or str(uuid4())
        existing = self.get("events", identifier)
        if existing:
            return existing
        return self.put("events", {
            "id": identifier, "post_id": post_id, "node": node,
            "choice": choice, "reason": reason,
            "evidence_ids": evidence_ids or [], "created_at": utcnow(),
        })

    def close(self):
        self.engine.dispose()
