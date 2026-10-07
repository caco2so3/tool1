from .db import get_conn

DEFAULTS = {
    "alert_time_weekday": "10:00",
    "alert_time_weekend": "09:00",
    "timezone": "Asia/Yekaterinburg",
    "diff_mode": "both",
    "tolerance_default": "0",
    "tolerance_percent": "0",
}


def get_setting(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")


def get_all_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = dict(DEFAULTS)
    for r in rows:
        out[r["key"]] = r["value"]
    return out


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )