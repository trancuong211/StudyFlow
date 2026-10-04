import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.tasks.models import Task
from apps.scheduler.progress import refresh_scheduled
from .models import PomodoroSession

DURATIONS = {'WORK': 25, 'SHORT_BREAK': 5, 'LONG_BREAK': 15}


def elapsed(session):
    seconds = session.elapsed_seconds
    if session.running_since:
        seconds += max(0, int((timezone.now()-session.running_since).total_seconds()))
    return min(seconds, session.target_minutes*60)


def state(session):
    if not session:
        return {'session': None}
    return {'session': {'id': session.pk, 'mode': session.session_type, 'task_id': session.task_id,
        'target_seconds': session.target_minutes*60, 'elapsed_seconds': elapsed(session),
        'running': session.running_since is not None, 'active': session.is_active,
        'completed': session.completed}, 'server_time': timezone.now().isoformat()}


@login_required
def timer_view(request):
    tasks = Task.objects.filter(user=request.user).exclude(status='COMPLETED')
    recent = PomodoroSession.objects.filter(user=request.user, is_active=False, end_time__isnull=False)[:10]
    return render(request, 'pomodoro/timer.html', {'tasks': tasks, 'recent_sessions': recent})


@login_required
def api_state(request):
    return JsonResponse(state(PomodoroSession.objects.filter(user=request.user, is_active=True).first()))


@login_required
@require_POST
@transaction.atomic
def api_start(request):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    existing = PomodoroSession.objects.filter(user=request.user, is_active=True).first()
    if existing:
        return JsonResponse(state(existing))
    try:
        data = json.loads(request.body)
        mode = data.get('session_type', 'WORK')
        if mode not in DURATIONS:
            raise ValueError
        task = None
        if data.get('task_id'):
            task = get_object_or_404(Task, user=request.user, pk=data['task_id'])
            if task.status == 'COMPLETED':
                return JsonResponse({'message': 'Công việc đã hoàn thành.'}, status=400)
        session = PomodoroSession.objects.create(user=request.user, task=task, session_type=mode,
            target_minutes=DURATIONS[mode], duration_minutes=0, start_time=timezone.now(),
            running_since=timezone.now(), completed=False, is_active=True)
        return JsonResponse(state(session))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'message': 'Dữ liệu phiên học không hợp lệ.'}, status=400)


@login_required
@require_POST
@transaction.atomic
def api_control(request, pk, action):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    session = get_object_or_404(PomodoroSession.objects.select_for_update(), user=request.user, pk=pk)
    if action not in ('pause', 'resume', 'finish', 'cancel'):
        return JsonResponse({'message': 'Thao tác không hợp lệ.'}, status=400)
    if not session.is_active:
        return JsonResponse(state(session))
    seconds = elapsed(session)
    if action == 'finish' and seconds < session.target_minutes*60:
        return JsonResponse({'message': 'Phiên chưa đủ thời gian. Tiếp tục timer hoặc đặt lại.'}, status=400)
    if action == 'pause':
        session.elapsed_seconds = seconds
        session.running_since = None
    elif action == 'resume':
        if session.running_since is None:
            session.running_since = timezone.now()
    else:
        session.elapsed_seconds = seconds
        session.running_since = None
        session.is_active = False
        session.end_time = timezone.now()
        session.duration_minutes = seconds//60
        session.completed = action == 'finish'
    session.save()
    if session.task_id:
        refresh_scheduled(session.task)
    return JsonResponse(state(session))


@login_required
@require_POST
def api_record_session(request):
    # Legacy endpoint must no longer trust client-supplied study duration.
    try:
        data = json.loads(request.body)
        pk = data.get('session_id')
        if not pk:
            return JsonResponse({'status': 'error', 'message': 'Hãy bắt đầu phiên qua timer trước khi ghi nhận.'}, status=400)
        return api_control(request, pk, 'finish')
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'error', 'message': 'Dữ liệu không hợp lệ.'}, status=400)
