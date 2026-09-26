from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'full_name', 'timezone', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Thông tin StudyFlow', {
            'fields': ('full_name', 'timezone', 'daily_study_goal_hours', 'is_google_connected')
        }),
    )
