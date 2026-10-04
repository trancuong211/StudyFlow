import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


class AuthenticationRateLimitMiddleware:
    """Shared Redis fixed-window limits; disabled by default in local development."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limits = {
            "/accounts/login/": (20, 300),
            "/accounts/register/": (10, 600),
            "/accounts/password/reset/": (5, 600),
        }
        rule = limits.get(request.path)
        if settings.AUTH_RATE_LIMIT_ENABLED and request.method == "POST" and rule:
            limit, window = rule
            identity = (
                request.META.get("REMOTE_ADDR", "")
                + ":"
                + request.POST.get("username", "").casefold()
            )
            digest = hashlib.sha256(identity.encode()).hexdigest()
            key = f"auth-limit:{request.path}:{int(time.time() // window)}:{digest}"
            try:
                cache.add(key, 0, timeout=window)
                attempts = cache.incr(key)
            except Exception:
                return HttpResponse(
                    "Tạm thời không thể đăng nhập. Vui lòng thử lại sau.", status=503
                )
            if attempts > limit:
                response = HttpResponse(
                    "Bạn đã thử quá nhiều lần. Vui lòng chờ vài phút rồi thử lại.",
                    status=429,
                )
                response["Retry-After"] = str(window)
                return response
        return self.get_response(request)
