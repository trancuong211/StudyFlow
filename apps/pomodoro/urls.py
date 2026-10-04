from django.urls import path
from . import views

app_name = 'pomodoro'

urlpatterns = [
    path('api/state/', views.api_state, name='api_state'),
    path('api/start/', views.api_start, name='api_start'),
    path('api/session/<int:pk>/<str:action>/', views.api_control, name='api_control'),
    path('', views.timer_view, name='timer'),
    path('api/record/', views.api_record_session, name='api_record'),
]
