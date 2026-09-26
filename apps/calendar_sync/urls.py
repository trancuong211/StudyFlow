from django.urls import path
from . import views

app_name = 'calendar_sync'

urlpatterns = [
    path('connect/', views.connect_google, name='connect'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'),
]
