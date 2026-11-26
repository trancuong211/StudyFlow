from django.contrib import admin

from .models import AIConfiguration, AIInsight


@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'insight_type', 'is_dismissed', 'created_at')
    list_filter = ('insight_type', 'is_dismissed', 'created_at')
    search_fields = ('title', 'content')


@admin.register(AIConfiguration)
class AIConfigurationAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'model_name', 'is_active', 'updated_at')
    list_filter = ('provider', 'is_active')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('key_hint', 'api_key_encrypted', 'created_at', 'updated_at')
