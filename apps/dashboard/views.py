from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum
from apps.courses.models import Course
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock
from apps.pomodoro.models import PomodoroSession
from apps.ai_assistant.models import AIInsight

@login_required
def index(request):
    """
    Dashboard tổng quan tiến độ học tập:
    - Thống kê môn học, task cần làm, deadline khẩn cấp
    - Tổng phút Pomodoro đã tập trung hôm nay
    - Cảnh báo mới nhất từ AI
    - Lịch học hôm nay
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Thống kê cơ bản
    total_courses = Course.objects.filter(user=request.user, is_active=True).count()
    pending_tasks = Task.objects.filter(
        user=request.user,
        status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
    )
    total_pending_tasks = pending_tasks.count()

    # Deadline trong vòng 3 ngày tới
    three_days_later = now + timezone.timedelta(days=3)
    urgent_deadlines = pending_tasks.filter(deadline__lte=three_days_later).order_by('deadline')[:5]

    # Tổng thời gian Pomodoro hôm nay
    today_pomodoro_mins = PomodoroSession.objects.filter(
        user=request.user,
        start_time__gte=today_start,
        completed=True
    ).aggregate(total=Sum('duration_minutes'))['total'] or 0

    # Các block học tập được xếp trong ngày hôm nay
    today_schedule_blocks = ScheduleBlock.objects.filter(
        user=request.user,
        start_time__gte=today_start,
        start_time__lte=today_end
    ).order_by('start_time')

    # AI Insight mới nhất
    latest_insight = AIInsight.objects.filter(user=request.user).first()

    context = {
        'total_courses': total_courses,
        'total_pending_tasks': total_pending_tasks,
        'urgent_deadlines': urgent_deadlines,
        'today_pomodoro_mins': today_pomodoro_mins,
        'today_schedule_blocks': today_schedule_blocks,
        'latest_insight': latest_insight,
    }
    return render(request, 'dashboard/index.html', context)
