import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .settings import get_setting

log = logging.getLogger("scheduler")
_sched: BackgroundScheduler | None = None


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _morning_job():
    # Заглушка. Реальную логику подключим после reports.py
    log.info("morning job tick (stub)")


def _weekly_close_job():
    # Заглушка. Реальную логику подключим после analytics.py
    log.info("weekly close tick (stub)")


def _build_jobs(sched: BackgroundScheduler):
    for j in sched.get_jobs():
        j.remove()

    tz = get_setting("timezone")
    wd_h, wd_m = _parse_hhmm(get_setting("alert_time_weekday"))
    we_h, we_m = _parse_hhmm(get_setting("alert_time_weekend"))

    sched.add_job(
        _morning_job,
        CronTrigger(day_of_week="mon-fri", hour=wd_h, minute=wd_m, timezone=tz),
        id="morning_weekday", replace_existing=True,
    )
    sched.add_job(
        _morning_job,
        CronTrigger(day_of_week="sat,sun", hour=we_h, minute=we_m, timezone=tz),
        id="morning_weekend", replace_existing=True,
    )
    sched.add_job(
        _weekly_close_job,
        CronTrigger(day_of_week="mon", hour=0, minute=5, timezone=tz),
        id="weekly_close", replace_existing=True,
    )

    log.info(
        "jobs rebuilt (weekday=%02d:%02d weekend=%02d:%02d tz=%s)",
        wd_h, wd_m, we_h, we_m, tz,
    )


def start_scheduler() -> BackgroundScheduler:
    global _sched
    tz = get_setting("timezone")
    _sched = BackgroundScheduler(timezone=tz)
    _build_jobs(_sched)
    _sched.start()
    return _sched


def reschedule():
    """Пересобирает джобы — вызывается при изменении настроек."""
    if _sched:
        _build_jobs(_sched)