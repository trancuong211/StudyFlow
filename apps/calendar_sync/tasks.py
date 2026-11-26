import logging

from celery import shared_task

from .models import GoogleCalendarToken
from .services import sync_calendar

logger = logging.getLogger(__name__)


@shared_task
def sync_connected_calendars():
    count = 0
    for token in GoogleCalendarToken.objects.filter(
        user__is_active=True
    ).select_related("user"):
        try:
            sync_calendar(token.user)
            count += 1
        except Exception:
            logger.warning(
                "Google sync failed for user %s; reconnect or retry", token.user_id
            )
    return count
