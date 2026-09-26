from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import AIInsight
from .services import AIServiceBridge

@login_required
def insights_view(request):
    """Trang xem danh sách các thông báo phân tích và cảnh báo của AI."""
    insights = AIInsight.objects.filter(user=request.user)
    return render(request, 'ai_assistant/insights.html', {'insights': insights})

@login_required
def generate_insight(request):
    """Kích hoạt yêu cầu AI phân tích lại lịch và deadline."""
    insight = AIServiceBridge.analyze_schedule_and_deadlines(request.user)
    messages.success(request, f'AI đã hoàn tất phân tích: {insight.title}')
    return redirect('ai_assistant:insights')
