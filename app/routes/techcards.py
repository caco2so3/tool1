from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_conn
from ..auth import require_admin, require_user
from ..calc_formula import calc_card

router = APIRouter()


class ItemIn(BaseModel):
    product_id: int
    qty_per_portion: float
    unit: str | None = None
    variant: str | None = None


class CardIn(BaseModel):
    name: str
    note: str | None = None
    method: str | None = None
    items: list[ItemIn]


class CardUpdate(BaseModel):
    name: str | None = None
    note: str | None = None
    method: str | None = None
    active: bool | None = None


class CalcIn(BaseModel):
    needed: float
    variant: str | None = None


def _card_items(conn, cid: int):
    return conn.execute(
        """SELECT tci.id, tci.product_id, tci.qty_per_portion, tci.unit,
                  tci.variant, p.name AS product_name
           FROM tech_card_items tci
           JOIN products p ON p.id = tci.product_id
           WHERE tci.card_id=? ORDER BY tci.id""",
        (cid,),
    ).fetchall()


def _serialize_card(c):
    return {
        "id": c["id"],
        "name": c["name"],
        "note": c["note"],
        "method": c["method"],
        "active": c["active"],
        "created_at": c["created_at"],
        "updated_at": c["updated_at"],
    }


@router.get("")
def list_cards(q: str | None = None, limit: int = 200, user=Depends(require_user)):
    """Список техкарт. Если q пуст — возвращаем пустой массив."""
    with get_conn() as conn:
        if not q or not q.strip():
            return []
        rows = conn.execute(
            "SELECT * FROM tech_cards WHERE active=1 AND name LIKE ? "
            "ORDER BY name LIMIT ?",
            (f"%{q}%", limit),
        ).fetchall()
        out = []
        for c in rows:
            items = _card_items(conn, c["id"])
            out.append({
                **_serialize_card(c),
                "items": [dict(i) for i in items],
            })
        return out


@router.get("/{cid}")
def get_card(cid: int, user=Depends(require_user)):
    with get_conn() as conn:
        c = conn.execute("SELECT * FROM tech_cards WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404)
        items = _card_items(conn, cid)
        return {**_serialize_card(c), "items": [dict(i) for i in items]}


@router.post("/{cid}/calc")
def calc(cid: int, body: CalcIn, user=Depends(require_user)):
    with get_conn() as conn:
        c = conn.execute("SELECT * FROM tech_cards WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404)
        items = _card_items(conn, cid)
    items_d = [dict(i) for i in items]
    if body.variant:
        items_d = [i for i in items_d if i["variant"] in (body.variant, None)]
    card = {**_serialize_card(c), "items": items_d}
    return calc_card(card, body.needed)


@router.post("")
def create_card(c: CardIn, user=Depends(require_admin)):
    name = c.name.strip()
    if not name:
        raise HTTPException(400, "пустое имя")
    if not c.items:
        raise HTTPException(400, "нет ингредиентов")
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO tech_cards(name, note, method, created_at, updated_at) "
                "VALUES(?,?,?,?,?)",
                (name, c.note, c.method, now, now),
            )
        except Exception:
            raise HTTPException(400, "имя занято")
        cid = cur.lastrowid
        for it in c.items:
            conn.execute(
                "INSERT INTO tech_card_items(card_id, product_id, qty_per_portion, unit, variant) "
                "VALUES(?,?,?,?,?)",
                (cid, it.product_id, it.qty_per_portion, it.unit, it.variant),
            )
        return {"id": cid}


@router.patch("/{cid}")
def update_card(cid: int, c: CardUpdate, user=Depends(require_admin)):
    fields, values = [], []
    for name, val in (
        ("name", c.name),
        ("note", c.note),
        ("method", c.method),
        ("active", None if c.active is None else int(c.active)),
    ):
        if val is not None:
            fields.append(f"{name}=?")
            values.append(val)
    if not fields:
        return {"ok": True}
    fields.append("updated_at=?")
    values.append(datetime.now(timezone.utc).isoformat())
    values.append(cid)
    with get_conn() as conn:
        conn.execute(f"UPDATE tech_cards SET {','.join(fields)} WHERE id=?", values)
    return {"ok": True}


@router.put("/{cid}/items")
def replace_items(cid: int, items: list[ItemIn], user=Depends(require_admin)):
    if not items:
        raise HTTPException(400, "нет ингредиентов")
    with get_conn() as conn:
        conn.execute("DELETE FROM tech_card_items WHERE card_id=?", (cid,))
        for it in items:
            conn.execute(
                "INSERT INTO tech_card_items(card_id, product_id, qty_per_portion, unit, variant) "
                "VALUES(?,?,?,?,?)",
                (cid, it.product_id, it.qty_per_portion, it.unit, it.variant),
            )
        conn.execute(
            "UPDATE tech_cards SET updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), cid),
        )
    return {"ok": True}


@router.delete("/{cid}")
def delete_card(cid: int, user=Depends(require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE tech_cards SET active=0 WHERE id=?", (cid,))
    return {"ok": True}