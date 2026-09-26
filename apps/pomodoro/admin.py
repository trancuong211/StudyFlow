from django.contrib import admin
from .models import PomodoroSession

@admin.register(PomodoroSession)
class PomodoroSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'task', 'session_type', 'duration_minutes', 'completed', 'start_time')
    list_filter = ('session_type', 'completed', 'start_time')
