from django.urls import path
from . import views

app_name = 'scheduler'

urlpatterns = [
    path('busy/', views.busy_list, name='busy_list'),
    path('busy/new/', views.busy_edit, name='busy_create'),
    path('busy/<int:pk>/edit/', views.busy_edit, name='busy_edit'),
    path('busy/<int:pk>/delete/', views.item_delete, {'kind': 'busy'}, name='busy_delete'),
    path('block/new/', views.block_edit, name='block_create'),
    path('block/<int:pk>/edit/', views.block_edit, name='block_edit'),
    path('block/<int:pk>/delete/', views.item_delete, {'kind': 'block'}, name='block_delete'),
    path('', views.calendar_view, name='calendar'),
    path('api/events/', views.api_events, name='api_events'),
    path('api/block/<int:pk>/update/', views.api_update_block, name='api_update_block'),
    path('api/block/<int:pk>/toggle-lock/', views.api_toggle_lock, name='api_toggle_lock'),
    path('auto-schedule/', views.trigger_auto_schedule, name='auto_schedule'),
]
