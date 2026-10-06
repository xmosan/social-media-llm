"""One cadence definition for scheduler jobs and saved-post schedule times."""

from datetime import datetime, timezone, timedelta
from apscheduler.triggers.cron import CronTrigger


def automation_triggers(account, automation):
    frequency = getattr(automation, "frequency", None) or "daily"
    days = {"daily": list(range(7)), "3x_weekly": [0, 2, 4], "weekly": [4]}.get(frequency)
    if frequency == "custom":
        mapping = {day: i for i, day in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))}
        selected = getattr(automation, "custom_days", None) or []
        if not selected or any(day not in mapping for day in selected):
            raise ValueError("Choose valid weekdays for a custom schedule")
        days = sorted({mapping[day] for day in selected})
    if days is None:
        raise ValueError("Unsupported automation frequency")
    try:
        hour, minute = map(int, (automation.post_time_local or account.daily_post_time or "09:00").split(":"))
        count = getattr(automation, "posts_per_day", None)
        spacing = getattr(automation, "post_spacing_hours", None)
        count = 1 if count is None else count
        spacing = 4 if spacing is None else spacing
        if not (0 <= hour < 24 and 0 <= minute < 60 and 1 <= count <= 24 and 1 <= spacing <= 24):
            raise ValueError
        if (count - 1) * spacing >= 24:
            raise ValueError
        zone = automation.timezone or account.timezone or "UTC"
        return [CronTrigger(hour=(hour + i * spacing) % 24, minute=minute,
                            day_of_week=",".join(str((day + (hour + i * spacing) // 24) % 7) for day in days),
                            timezone=zone) for i in range(count)]
    except (TypeError, ValueError, KeyError) as error:
        raise ValueError("Use a valid time, timezone, and distinct daily posting slots") from error


def next_automation_time(account, automation, now=None):
    now = now or datetime.now(timezone.utc)
    after = now + timedelta(microseconds=1)
    candidates = [trigger.get_next_fire_time(None, after) for trigger in automation_triggers(account, automation)]
    return min(candidate.astimezone(timezone.utc) for candidate in candidates if candidate is not None)
