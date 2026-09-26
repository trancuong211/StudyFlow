from django.urls import path
from . import views

app_name = 'scheduler'

urlpatterns = [
    path('', views.calendar_view, name='calendar'),
    path('api/events/', views.api_events, name='api_events'),
    path('api/block/<int:pk>/update/', views.api_update_block, name='api_update_block'),
    path('api/block/<int:pk>/toggle-lock/', views.api_toggle_lock, name='api_toggle_lock'),
    path('auto-schedule/', views.trigger_auto_schedule, name='auto_schedule'),
]
