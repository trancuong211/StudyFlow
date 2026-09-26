import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import PomodoroSession
from apps.tasks.models import Task

@login_required
def timer_view(request):
    """Màn hình đồng hồ Pomodoro tương tác trực quan."""
    tasks = Task.objects.filter(
        user=request.user,
        status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
    )
    recent_sessions = PomodoroSession.objects.filter(user=request.user)[:10]
    return render(request, 'pomodoro/timer.html', {
        'tasks': tasks,
        'recent_sessions': recent_sessions
    })

@login_required
@require_POST
def api_record_session(request):
    """API lưu kết quả một phiên Pomodoro vừa hoàn tất."""
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        task = None
        if task_id:
            task = Task.objects.filter(id=task_id, user=request.user).first()

        session = PomodoroSession.objects.create(
            user=request.user,
            task=task,
            session_type=data.get('session_type', PomodoroSession.SessionType.WORK),
            duration_minutes=int(data.get('duration_minutes', 25)),
            start_time=timezone.now() - timezone.timedelta(minutes=int(data.get('duration_minutes', 25))),
            end_time=timezone.now(),
            completed=data.get('completed', True),
            notes=data.get('notes', '')
        )
        return JsonResponse({
            'status': 'success',
            'session_id': session.id,
            'duration': session.duration_minutes
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
