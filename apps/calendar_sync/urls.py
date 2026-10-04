from django.urls import path
from . import views

app_name = 'calendar_sync'

urlpatterns = [
    path('', views.calendar_settings, name='settings'),
    path('sync/', views.sync_now, name='sync'),
    path('disconnect/', views.disconnect, name='disconnect'),
    path('connect/', views.connect_google, name='connect'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'),
]
