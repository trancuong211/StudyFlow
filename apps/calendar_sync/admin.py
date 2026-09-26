from django.contrib import admin
from .models import GoogleCalendarToken

@admin.register(GoogleCalendarToken)
class GoogleCalendarTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'calendar_id', 'last_synced_at', 'created_at')
    search_fields = ('user__username', 'calendar_id')
