from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_conn

router = APIRouter()


class ItemIn(BaseModel):
    product_id: int
    qty: float


class EventIn(BaseModel):
    event_type: str
    items: list[ItemIn]
    note: str | None = None


@router.get("/products")
def list_products():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, unit, ref_qty FROM products "
            "WHERE active=1 AND track_stock=1 ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/balance")
def current_balance():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.unit,
              (SELECT qty FROM stock_events e
                WHERE e.product_id = p.id AND e.event_type='stocktake'
                ORDER BY e.occurred_at DESC LIMIT 1) AS last_qty
            FROM products p
            WHERE p.active=1 AND p.track_stock=1
            ORDER BY p.name
            """
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/events")
def submit_events(data: EventIn):
    if data.event_type not in ("stocktake", "intake", "writeoff"):
        raise HTTPException(400, "bad event_type")
    if not data.items:
        raise HTTPException(400, "empty items")

    now = datetime.now(timezone.utc).isoformat()
    batch = str(uuid4()) if data.event_type == "stocktake" else None

    with get_conn() as conn:
        for it in data.items:
            conn.execute(
                "INSERT INTO stock_events(product_id, event_type, qty, batch_id, occurred_at, note) "
                "VALUES(?,?,?,?,?,?)",
                (it.product_id, data.event_type, it.qty, batch, now, data.note),
            )
    return {
        "ok": True,
        "batch_id": batch,
        "occurred_at": now,
        "count": len(data.items),
    }