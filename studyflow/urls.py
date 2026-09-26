from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.dashboard.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('courses/', include('apps.courses.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('scheduler/', include('apps.scheduler.urls')),
    path('pomodoro/', include('apps.pomodoro.urls')),
    path('calendar/', include('apps.calendar_sync.urls')),
    path('ai/', include('apps.ai_assistant.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
