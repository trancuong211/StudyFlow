from django.contrib import admin
from .models import ScheduleBlock

@admin.register(ScheduleBlock)
class ScheduleBlockAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'start_time', 'end_time', 'is_auto_generated', 'is_locked')
    list_filter = ('is_auto_generated', 'is_locked', 'start_time')
    search_fields = ('title', 'notes')
