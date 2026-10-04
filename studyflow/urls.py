from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .health import health

urlpatterns = [
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('', include('apps.dashboard.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('courses/', include('apps.courses.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('scheduler/', include('apps.scheduler.urls')),
    path('pomodoro/', include('apps.pomodoro.urls')),
    path('calendar/', include('apps.calendar_sync.urls')),
    path('ai/', include('apps.ai_assistant.urls')),
    path('resources/', include('apps.resources.urls')),
    path('notifications/', include('apps.notifications.urls')),
]

# Uploaded study materials are served only by the authenticated download view.
