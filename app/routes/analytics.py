from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..auth import require_admin

router = APIRouter()
TZ_EKB = timezone(timedelta(hours=5))


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _week_start_ekb(dt: datetime) -> datetime:
    return (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _current_week_start():
    return _week_start_ekb(datetime.now(TZ_EKB))


def _movements_for_product(conn, product_id: int, from_dt: datetime, to_dt: datetime):
    from_iso = _iso_utc(from_dt)
    to_iso = _iso_utc(to_dt)

    beg = conn.execute(
        "SELECT qty FROM stock_events WHERE product_id=? AND event_type='stocktake' "
        "AND occurred_at < ? ORDER BY occurred_at DESC LIMIT 1",
        (product_id, from_iso),
    ).fetchone()
    end = conn.execute(
        "SELECT qty FROM stock_events WHERE product_id=? AND event_type='stocktake' "
        "AND occurred_at >= ? AND occurred_at < ? "
        "ORDER BY occurred_at DESC LIMIT 1",
        (product_id, from_iso, to_iso),
    ).fetchone()
    intake = conn.execute(
        "SELECT COALESCE(SUM(qty),0) s FROM stock_events "
        "WHERE product_id=? AND event_type='intake' "
        "AND occurred_at >= ? AND occurred_at < ?",
        (product_id, from_iso, to_iso),
    ).fetchone()["s"]
    writeoff = conn.execute(
        "SELECT COALESCE(SUM(qty),0) s FROM stock_events "
        "WHERE product_id=? AND event_type='writeoff' "
        "AND occurred_at >= ? AND occurred_at < ?",
        (product_id, from_iso, to_iso),
    ).fetchone()["s"]

    beginning = beg["qty"] if beg else None
    ending = end["qty"] if end else None

    consumption = None
    if beginning is not None and ending is not None:
        consumption = beginning + intake - writeoff - ending

    return {
        "beginning": beginning,
        "intake": intake,
        "writeoff": writeoff,
        "ending": ending,
        "consumption": consumption,
    }


def build_weekly_report(week_start_dt: datetime, force: bool = False):
    week_start_dt = week_start_dt.astimezone(TZ_EKB)
    week_end_dt = week_start_dt + timedelta(days=7)
    ws = week_start_dt.date().isoformat()
    we = (week_end_dt - timedelta(days=1)).date().isoformat()

    prev_start = week_start_dt - timedelta(days=7)
    prev_end = week_start_dt

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM weekly_reports WHERE week_start=?", (ws,)
        ).fetchone()
        if existing and not force:
            return existing["id"]
        if existing and force:
            conn.execute("DELETE FROM weekly_reports WHERE id=?", (existing["id"],))

        now_iso = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO weekly_reports(week_start, week_end, generated_at, is_final) "
            "VALUES(?,?,?,1)",
            (ws, we, now_iso),
        )
        rid = cur.lastrowid

        products = conn.execute(
            "SELECT id, name, unit FROM products "
            "WHERE active=1 AND track_stock=1 ORDER BY name"
        ).fetchall()

        for p in products:
            pid = p["id"]
            m = _movements_for_product(conn, pid, week_start_dt, week_end_dt)
            prev = _movements_for_product(conn, pid, prev_start, prev_end)

            prev_cons = prev["consumption"]
            trend_diff = None
            trend_pct = None
            if m["consumption"] is not None and prev_cons is not None:
                trend_diff = m["consumption"] - prev_cons
                if prev_cons != 0:
                    trend_pct = (trend_diff / abs(prev_cons)) * 100.0

            conn.execute(
                """INSERT INTO weekly_report_items
                   (report_id, product_id, name_snapshot, unit_snapshot,
                    beginning, intake, writeoff, ending, consumption,
                    prev_consumption, trend_diff, trend_pct)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, pid, p["name"], p["unit"],
                 m["beginning"], m["intake"], m["writeoff"], m["ending"],
                 m["consumption"], prev_cons, trend_diff, trend_pct),
            )
        return rid


@router.get("/weekly")
def list_weeks(limit: int = Query(26, ge=1, le=200)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, week_start, week_end, generated_at, is_final "
            "FROM weekly_reports ORDER BY week_start DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/weekly/live")
def current_week_live():
    start = _current_week_start()
    end = start + timedelta(days=7)
    with get_conn() as conn:
        products = conn.execute(
            "SELECT id, name, unit FROM products "
            "WHERE active=1 AND track_stock=1 ORDER BY name"
        ).fetchall()
        items = []
        for p in products:
            m = _movements_for_product(conn, p["id"], start, end)
            items.append({
                "product_id": p["id"],
                "name": p["name"],
                "unit": p["unit"],
                **m,
                "prev_consumption": None,
                "trend_diff": None,
                "trend_pct": None,
            })
        return {
            "week_start": start.date().isoformat(),
            "week_end": (end - timedelta(days=1)).date().isoformat(),
            "is_live": True,
            "items": items,
        }


@router.get("/weekly/{week_start}")
def get_week(week_start: str):
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM weekly_reports WHERE week_start=?", (week_start,)
        ).fetchone()
        if not r:
            raise HTTPException(404, "week not found")
        items = conn.execute(
            "SELECT * FROM weekly_report_items WHERE report_id=? ORDER BY name_snapshot",
            (r["id"],),
        ).fetchall()
        return {
            "week_start": r["week_start"],
            "week_end": r["week_end"],
            "generated_at": r["generated_at"],
            "is_live": False,
            "items": [dict(i) for i in items],
        }


@router.post("/weekly/rebuild")
def rebuild_week(week_start: str | None = None):
    if week_start:
        y, m, d = map(int, week_start.split("-"))
        start = datetime(y, m, d, tzinfo=TZ_EKB)
    else:
        start = _current_week_start() - timedelta(days=7)
    rid = build_weekly_report(start, force=True)
    return {"ok": True, "report_id": rid, "week_start": start.date().isoformat()}


@router.get("/trend")
def trend(limit: int = Query(12, ge=1, le=52)):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT wr.week_start,
                      COALESCE(SUM(wri.consumption),0) AS total,
                      COALESCE(SUM(wri.trend_diff),0)  AS diff
               FROM weekly_reports wr
               LEFT JOIN weekly_report_items wri ON wri.report_id = wr.id
               GROUP BY wr.id
               ORDER BY wr.week_start DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- debug: список движений и удаление ---

@router.get("/events")
def list_events(limit: int = Query(100, ge=1, le=1000), product_id: int | None = None):
    with get_conn() as conn:
        if product_id:
            rows = conn.execute(
                """SELECT e.id, e.event_type, e.qty, e.occurred_at, e.note,
                          p.name, p.unit
                   FROM stock_events e
                   JOIN products p ON p.id = e.product_id
                   WHERE e.product_id=?
                   ORDER BY e.occurred_at DESC LIMIT ?""",
                (product_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT e.id, e.event_type, e.qty, e.occurred_at, e.note,
                          p.name, p.unit
                   FROM stock_events e
                   JOIN products p ON p.id = e.product_id
                   ORDER BY e.occurred_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


@router.delete("/events/{eid}")
def delete_event(eid: int, user=Depends(require_admin)):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM stock_events WHERE id=?", (eid,)).fetchone()
        if not row:
            raise HTTPException(404, "event not found")
        conn.execute("DELETE FROM stock_events WHERE id=?", (eid,))
        return {"ok": True}


@router.get("/monthly/{ym}")
def monthly(ym: str):
    """ym = 'YYYY-MM'. Считаем на лету, без сохранения."""
    try:
        y, m = map(int, ym.split("-"))
    except Exception:
        raise HTTPException(400, "bad month format")
    start = datetime(y, m, 1, tzinfo=TZ_EKB)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=TZ_EKB)
    else:
        end = datetime(y, m + 1, 1, tzinfo=TZ_EKB)

    with get_conn() as conn:
        products = conn.execute(
            "SELECT id, name, unit FROM products "
            "WHERE active=1 AND track_stock=1 ORDER BY name"
        ).fetchall()
        items = []
        for p in products:
            mv = _movements_for_product(conn, p["id"], start, end)
            items.append({
                "product_id": p["id"], "name": p["name"], "unit": p["unit"], **mv,
            })
        return {
            "month": ym,
            "from": start.date().isoformat(),
            "to": (end - timedelta(days=1)).date().isoformat(),
            "items": items,
        }