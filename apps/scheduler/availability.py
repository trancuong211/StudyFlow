from datetime import datetime, timedelta

from apps.accounts.timezones import user_zone


def recurring_intervals(period, start, end):
    """Expand weekly events in the owner's timezone, including boundary overlaps."""
    if not period.repeats_weekly:
        return (
            [(period.start_time, period.end_time)]
            if period.start_time < end and period.end_time > start
            else []
        )
    zone = user_zone(period.user)
    original_start = period.start_time.astimezone(zone)
    original_end = period.end_time.astimezone(zone)
    duration = original_end.replace(tzinfo=None) - original_start.replace(tzinfo=None)
    first_day = original_start.date()
    weeks = max(0, ((start.astimezone(zone).date() - first_day).days // 7) - 1)
    current = first_day + timedelta(weeks=weeks)
    intervals = []
    while current <= end.astimezone(zone).date():
        if period.repeat_until and current > period.repeat_until:
            break
        local_start = datetime.combine(current, original_start.timetz()).replace(
            tzinfo=zone
        )
        local_end = (local_start.replace(tzinfo=None) + duration).replace(tzinfo=zone)
        if local_start < end and local_end > start:
            intervals.append((local_start, local_end))
        current += timedelta(days=7)
    return intervals


def busy_intervals(user, start, end):
    from apps.calendar_sync.models import GoogleCalendarEvent

    from .models import BusyPeriod

    intervals = []
    for period in BusyPeriod.objects.filter(
        user=user, start_time__lt=end
    ).select_related("user"):
        intervals.extend(recurring_intervals(period, start, end))
    intervals.extend(
        GoogleCalendarEvent.objects.filter(
            user=user, start_time__lt=end, end_time__gt=start, is_busy=True
        ).values_list("start_time", "end_time")
    )
    return intervals
