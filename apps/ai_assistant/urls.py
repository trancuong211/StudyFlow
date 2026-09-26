from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.insights_view, name='insights'),
    path('analyze/', views.generate_insight, name='generate_insight'),
]
