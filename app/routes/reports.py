from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from ..db import get_conn

router = APIRouter()


def _last_stocktake(conn, product_id, before_iso=None, after_iso=None):
    q = "SELECT qty, occurred_at FROM stock_events WHERE product_id=? AND event_type='stocktake'"
    args = [product_id]
    if before_iso:
        q += " AND occurred_at < ?"
        args.append(before_iso)
    if after_iso:
        q += " AND occurred_at >= ?"
        args.append(after_iso)
    q += " ORDER BY occurred_at DESC LIMIT 1"
    return conn.execute(q, args).fetchone()


def _intake_sum(conn, product_id, from_iso, to_iso):
    row = conn.execute(
        "SELECT COALESCE(SUM(qty),0) s FROM stock_events "
        "WHERE product_id=? AND event_type='intake' AND occurred_at>=? AND occurred_at<?",
        (product_id, from_iso, to_iso),
    ).fetchone()
    return row["s"]


def generate_report():
    now = datetime.now(timezone.utc)
    period_to = now.isoformat()
    period_from = (now - timedelta(hours=24)).isoformat()

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reports(generated_at, period_from, period_to) VALUES(?,?,?)",
            (now.isoformat(), period_from, period_to),
        )
        rid = cur.lastrowid

        products = conn.execute(
            "SELECT id, ref_qty, tol_abs, tol_pct FROM products "
            "WHERE active=1 AND track_stock=1"
        ).fetchall()

        for p in products:
            pid = p["id"]
            ref = p["ref_qty"]
            tol = max(p["tol_abs"] or 0, ref * (p["tol_pct"] or 0) / 100)

            end = _last_stocktake(conn, pid, after_iso=period_from)
            beg = _last_stocktake(conn, pid, before_iso=period_from)
            intake = _intake_sum(conn, pid, period_from, period_to)

            fact = end["qty"] if end else None
            beginning = beg["qty"] if beg else None

            if fact is None:
                status, diff = "missing", None
            else:
                diff = fact - ref
                if abs(diff) <= tol:
                    status = "ok"
                elif diff < 0:
                    status = "shortage"
                else:
                    status = "surplus"

            consumption = None
            if beginning is not None and fact is not None:
                consumption = beginning + intake - fact

            conn.execute(
                """INSERT INTO report_items
                   (report_id, product_id, ref_qty, fact_qty, diff, tolerance, status,
                    intake_sum, consumption, beginning_qty)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (rid, pid, ref, fact, diff, tol, status, intake, consumption, beginning),
            )
        return rid


@router.post("/generate")
def force_generate():
    return {"report_id": generate_report()}


@router.get("")
def list_reports():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, generated_at, period_from, period_to, acknowledged "
            "FROM reports ORDER BY id DESC LIMIT 60"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/latest")
def latest():
    with get_conn() as conn:
        r = conn.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()
        if not r:
            return None
    return _detail(r["id"])


@router.get("/{rid}")
def get_report(rid: int):
    return _detail(rid)


@router.post("/{rid}/ack")
def ack(rid: int):
    with get_conn() as conn:
        conn.execute("UPDATE reports SET acknowledged=1 WHERE id=?", (rid,))
    return {"ok": True}


def _detail(rid):
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404)
        items = conn.execute(
            """SELECT ri.*, p.name, p.unit
               FROM report_items ri
               JOIN products p ON p.id = ri.product_id
               WHERE ri.report_id=? ORDER BY p.name""",
            (rid,),
        ).fetchall()
        return {**dict(r), "items": [dict(i) for i in items]}