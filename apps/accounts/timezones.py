from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


def user_zone(user):
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return timezone.get_default_timezone()


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with timezone.override(
            user_zone(request.user)
            if request.user.is_authenticated
            else timezone.get_default_timezone()
        ):
            return self.get_response(request)
