from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'course', 'priority', 'status', 'deadline', 'is_scheduled')
    list_filter = ('status', 'priority', 'is_scheduled', 'deadline')
    search_fields = ('title', 'description')
