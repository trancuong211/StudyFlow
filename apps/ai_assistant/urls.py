from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('summary/', views.generate_summary, name='daily_summary'),
    path('<int:pk>/dismiss/', views.dismiss, name='dismiss'),
    path('', views.insights_view, name='insights'),
    path('analyze/', views.generate_insight, name='generate_insight'),
]
