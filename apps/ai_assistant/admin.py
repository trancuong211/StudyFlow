from django.contrib import admin
from .models import AIInsight

@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'insight_type', 'is_dismissed', 'created_at')
    list_filter = ('insight_type', 'is_dismissed', 'created_at')
    search_fields = ('title', 'content')
