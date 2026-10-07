from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_conn
from ..auth import require_admin
from ..settings import get_all_settings, set_setting
from ..scheduler import reschedule

router = APIRouter()


class ProductIn(BaseModel):
    name: str
    unit: str = "шт"
    ref_qty: float = 0
    tol_abs: float = 0
    tol_pct: float = 0
    track_stock: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    tol_abs: float | None = None
    tol_pct: float | None = None
    active: bool | None = None
    track_stock: bool | None = None


class RefUpdate(BaseModel):
    ref_qty: float
    note: str | None = None


class SettingsIn(BaseModel):
    alert_time_weekday: str | None = None
    alert_time_weekend: str | None = None
    timezone: str | None = None
    diff_mode: str | None = None


@router.get("/products")
def list_all(user=Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, unit, ref_qty, tol_abs, tol_pct, track_stock, active "
            "FROM products ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/products")
def create_product(p: ProductIn, user=Depends(require_admin)):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO products(name, unit, ref_qty, tol_abs, tol_pct, track_stock, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    p.name.strip(),
                    p.unit,
                    p.ref_qty,
                    p.tol_abs,
                    p.tol_pct,
                    int(p.track_stock),
                    now,
                ),
            )
        except Exception:
            raise HTTPException(400, "имя занято")
        return {"id": cur.lastrowid}


@router.patch("/products/{pid}")
def update_product(pid: int, p: ProductUpdate, user=Depends(require_admin)):
    fields, values = [], []
    for name, val in (
        ("name", p.name),
        ("unit", p.unit),
        ("tol_abs", p.tol_abs),
        ("tol_pct", p.tol_pct),
        ("active", None if p.active is None else int(p.active)),
        ("track_stock", None if p.track_stock is None else int(p.track_stock)),
    ):
        if val is not None:
            fields.append(f"{name}=?")
            values.append(val)
    if not fields:
        return {"ok": True}
    values.append(pid)
    with get_conn() as conn:
        conn.execute(f"UPDATE products SET {','.join(fields)} WHERE id=?", values)
    return {"ok": True}


@router.delete("/products/{pid}")
def deactivate(pid: int, user=Depends(require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    return {"ok": True}


@router.put("/products/{pid}/ref")
def set_ref(pid: int, r: RefUpdate, user=Depends(require_admin)):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT ref_qty FROM products WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404)
        old = row["ref_qty"]
        conn.execute("UPDATE products SET ref_qty=? WHERE id=?", (r.ref_qty, pid))
        conn.execute(
            "INSERT INTO ref_history(product_id, old_qty, new_qty, changed_at, note) "
            "VALUES(?,?,?,?,?)",
            (pid, old, r.ref_qty, now, r.note),
        )
    return {"ok": True, "old": old, "new": r.ref_qty}


@router.get("/products/{pid}/ref-history")
def ref_history(pid: int, limit: int = 30, user=Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT old_qty, new_qty, changed_at, note FROM ref_history "
            "WHERE product_id=? ORDER BY id DESC LIMIT ?",
            (pid, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/settings")
def read_settings(user=Depends(require_admin)):
    return get_all_settings()


@router.patch("/settings")
def update_settings(s: SettingsIn, user=Depends(require_admin)):
    for k, v in s.model_dump(exclude_none=True).items():
        set_setting(k, str(v))
    reschedule()
    return {"ok": True, "settings": get_all_settings()}