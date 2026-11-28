from django import template
from django.utils import timezone

register = template.Library()

_UNITS = (
    (365 * 24 * 3600, "năm"),
    (30 * 24 * 3600, "tháng"),
    (7 * 24 * 3600, "tuần"),
    (24 * 3600, "ngày"),
    (3600, "giờ"),
    (60, "phút"),
)


@register.filter
def vi_timesince(value, arg=None):
    if not value:
        return ""

    now = arg or timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())

    seconds = int((now - value).total_seconds())
    if seconds < 60:
        return "vừa xong"

    parts = []
    for unit_seconds, label in _UNITS:
        count, seconds = divmod(seconds, unit_seconds)
        if count:
            parts.append(f"{count} {label}")
        if len(parts) == 2:
            break

    if not parts:
        return "vừa xong"
    return ", ".join(parts) + " trước"
