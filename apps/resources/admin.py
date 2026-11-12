from django.contrib import admin

from .models import StudyResource


@admin.register(StudyResource)
class StudyResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "course", "created_at")
    search_fields = ("title", "user__username")
