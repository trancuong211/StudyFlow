from django.contrib import admin
from .models import Course

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'user', 'color', 'credits', 'is_active', 'created_at')
    list_filter = ('is_active', 'semester')
    search_fields = ('name', 'code', 'instructor')
