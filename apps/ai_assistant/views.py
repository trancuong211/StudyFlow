from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import AIInsight
from .services import AIServiceBridge
from .services import habit_analysis
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from .planning import apply_proposal, risk_cards

@login_required
def insights_view(request):
    """Trang xem danh sách các thông báo phân tích và cảnh báo của AI."""
    insights = AIInsight.objects.filter(user=request.user, is_dismissed=False)[:50]
    selected_task = request.GET.get('task', '')
    selected_task = int(selected_task) if (selected_task.isascii() and selected_task.isdigit()
        and len(selected_task) <= 19 and 0 < int(selected_task) <= 2**63-1) else None
    cards, extra = risk_cards(request.user, task_id=selected_task)
    return render(request, 'ai_assistant/insights.html', {'insights': insights,
        'habits': habit_analysis(request.user), 'risk_cards': cards, 'extra_risks': extra})


@login_required
@require_POST
def apply_schedule_suggestion(request):
    token = request.POST.get('token', '')
    if not token or len(token) > 10000:
        messages.error(request, 'Thiếu gợi ý hợp lệ. Hãy tải lại trang.')
        return redirect('ai_assistant:insights')
    try:
        block = apply_proposal(request.user, token)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, f'Đã áp dụng và khóa khung học: {block.title}.')
    return redirect('ai_assistant:insights')

@login_required
@require_POST
def generate_insight(request):
    """Kích hoạt yêu cầu AI phân tích lại lịch và deadline."""
    insight = AIServiceBridge.analyze_schedule_and_deadlines(request.user)
    messages.success(request, f'AI đã hoàn tất phân tích: {insight.title}')
    return redirect('ai_assistant:insights')


@login_required
@require_POST
def generate_summary(request):
    AIServiceBridge.daily_summary(request.user)
    messages.success(request, 'Đã cập nhật tóm tắt hôm nay.')
    return redirect('ai_assistant:insights')


@login_required
@require_POST
def dismiss(request, pk):
    insight = get_object_or_404(AIInsight, pk=pk, user=request.user)
    insight.is_dismissed = True
    insight.save(update_fields=['is_dismissed'])
    return redirect('ai_assistant:insights')
