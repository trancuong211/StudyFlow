from django.urls import path
from . import views

app_name = 'pomodoro'

urlpatterns = [
    path('', views.timer_view, name='timer'),
    path('api/record/', views.api_record_session, name='api_record'),
]
