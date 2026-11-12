from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from apps.courses.models import Course
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock
from apps.pomodoro.models import PomodoroSession
from apps.ai_assistant.models import AIInsight
from apps.ai_assistant.services import habit_analysis

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
    # Đầu/cuối ngày theo giờ địa phương (TIME_ZONE = Asia/Ho_Chi_Minh)
    local_now = timezone.localtime(now)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Thống kê cơ bản
    total_courses = Course.objects.filter(user=request.user, is_active=True).count()
    pending_tasks = Task.objects.filter(
        user=request.user,
        status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
    )
    total_pending_tasks = pending_tasks.count()

    # Deadline trong vòng 3 ngày tới
    three_days_later = now + timedelta(days=3)
    urgent_deadlines = pending_tasks.filter(deadline__lte=three_days_later).order_by('deadline')[:5]

    # Tổng thời gian Pomodoro hôm nay
    today_pomodoro_mins = PomodoroSession.objects.filter(
        user=request.user,
        start_time__gte=today_start,
        start_time__lte=today_end,
        session_type=PomodoroSession.SessionType.WORK,
        completed=True
    ).aggregate(total=Sum('duration_minutes'))['total'] or 0

    # Các block học tập được xếp trong ngày hôm nay
    today_schedule_blocks = ScheduleBlock.objects.filter(
        user=request.user,
        start_time__gte=today_start,
        start_time__lte=today_end
    ).order_by('start_time')

    # AI Insight mới nhất
    latest_insight = AIInsight.objects.filter(user=request.user, is_dismissed=False).first()

    context = {
        'total_courses': total_courses,
        'total_pending_tasks': total_pending_tasks,
        'urgent_deadlines': urgent_deadlines,
        'today_pomodoro_mins': today_pomodoro_mins,
        'today_schedule_blocks': today_schedule_blocks,
        'latest_insight': latest_insight,
        'habits': habit_analysis(request.user),
        'daily_summary': AIInsight.objects.filter(user=request.user, insight_type='DAILY_SUMMARY', created_at__gte=today_start, is_dismissed=False).first(),
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, 'dashboard/index.html', context)
