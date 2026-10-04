import json
from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.tasks.models import Task
from apps.calendar_sync.models import GoogleCalendarEvent
from .models import ScheduleBlock, BusyPeriod
from .forms import BusyPeriodForm, BlockForm
from .availability import recurring_intervals, busy_intervals
from .progress import remaining_minutes, planned_minutes, refresh_scheduled
from .engine.optimizer import ScheduleOptimizer


def _parse_datetime(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


@login_required
def calendar_view(request):
    report = []
    load = ScheduleOptimizer(request.user)._daily_load()
    cap = request.user.daily_study_goal_hours * 60
    overloaded_days = [{'date': day, 'minutes': minutes, 'extra': minutes-cap}
                       for day, minutes in sorted(load.items()) if minutes > cap]
    for task in Task.objects.filter(user=request.user).exclude(status='COMPLETED'):
        missing = max(0, remaining_minutes(task)-planned_minutes(task))
        if missing:
            report.append({'task_id': task.pk, 'title': task.title, 'missing_minutes': missing,
                'reason': 'Đã quá deadline' if task.is_overdue else 'Chưa có đủ khung học trước deadline'})
    return render(request, 'scheduler/calendar.html', {'schedule_report': report, 'overloaded_days': overloaded_days})


@login_required
def api_events(request):
    try:
        start = _parse_datetime(request.GET['start']) if request.GET.get('start') else timezone.now()-timedelta(days=7)
        end = _parse_datetime(request.GET['end']) if request.GET.get('end') else start+timedelta(days=45)
        if end <= start or end-start > timedelta(days=95):
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'message': 'Khoảng xem lịch không hợp lệ (tối đa 95 ngày).'}, status=400)
    events = []
    busy = busy_intervals(request.user, start, end)
    for b in ScheduleBlock.objects.filter(user=request.user, start_time__lt=end, end_time__gt=start).select_related('task__course'):
        color = b.task.course.color if b.task and b.task.course else '#2563eb'
        conflict = any(a < b.end_time and finish > b.start_time for a, finish in busy)
        if conflict:
            color = '#b91c1c'
        events.append({'id': b.pk, 'title': ('⚠ ' if conflict else '') + b.title, 'start': b.start_time.isoformat(), 'end': b.end_time.isoformat(),
            'backgroundColor': color, 'borderColor': '#1e3a8a' if b.is_locked else color,
            'extendedProps': {'taskId': b.task_id, 'isLocked': b.is_locked, 'isAuto': b.is_auto_generated,
                              'notes': ('Trùng lịch bận / Google Calendar. Hãy chỉnh khung hoặc lập lại lịch. ' if conflict else '') + b.notes,
                              'hasConflict': conflict, 'kind': 'study'}})
    for period in BusyPeriod.objects.filter(user=request.user, start_time__lt=end).select_related('user'):
        for a, b in recurring_intervals(period, start, end):
            events.append({'id': f'busy-{period.pk}-{a.isoformat()}', 'title': period.title,
                'start': a.isoformat(), 'end': b.isoformat(), 'editable': False, 'backgroundColor': '#64748b',
                'extendedProps': {'kind': 'busy', 'editUrl': f'/scheduler/busy/{period.pk}/edit/'}})
    for event in GoogleCalendarEvent.objects.filter(user=request.user, start_time__lt=end, end_time__gt=start):
        events.append({'id': f'google-{event.pk}', 'title': event.title, 'start': event.start_time.isoformat(),
            'end': event.end_time.isoformat(), 'editable': False, 'backgroundColor': '#059669',
            'extendedProps': {'kind': 'google'}})
    return JsonResponse(events, safe=False)


@login_required
@require_POST
@transaction.atomic
def api_update_block(request, pk):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    block = get_object_or_404(ScheduleBlock.objects.select_related('task'), pk=pk, user=request.user)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        if data.get('start') is not None:
            block.start_time = _parse_datetime(data['start'])
        if data.get('end') is not None:
            block.end_time = _parse_datetime(data['end'])
        if data.get('lock_on_edit', True):
            block.is_locked = True
        block.full_clean()
        block.save()
        if block.task_id:
            refresh_scheduled(block.task)
        return JsonResponse({'status': 'success', 'is_locked': block.is_locked})
    except ValidationError as exc:
        return JsonResponse({'status': 'error', 'message': ' '.join(exc.messages)}, status=400)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'error', 'message': 'Dữ liệu thời gian không hợp lệ.'}, status=400)


@login_required
@require_POST
@transaction.atomic
def api_toggle_lock(request, pk):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    block = get_object_or_404(ScheduleBlock.objects.select_for_update(), pk=pk, user=request.user)
    block.is_locked = not block.is_locked
    block.save(update_fields=['is_locked'])
    return JsonResponse({'status': 'success', 'is_locked': block.is_locked})


@login_required
@require_POST
def trigger_auto_schedule(request):
    optimizer = ScheduleOptimizer(request.user)
    created = optimizer.run()
    messages.success(request, f'Đã xếp {len(created)} khung học trong 7 ngày tới.')
    if optimizer.report:
        messages.warning(request, f'{len(optimizer.report)} công việc chưa đủ thời gian. Xem chi tiết bên dưới lịch.')
    return redirect('scheduler:calendar')


@login_required
def busy_list(request):
    return render(request, 'scheduler/busy_list.html', {'periods': BusyPeriod.objects.filter(user=request.user)})


@login_required
@transaction.atomic
def busy_edit(request, pk=None):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    item = get_object_or_404(BusyPeriod, pk=pk, user=request.user) if pk else None
    form = BusyPeriodForm(request.POST if request.method == 'POST' else None, instance=item, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã lưu lịch bận. Bạn có thể chạy lại lập lịch để cập nhật kế hoạch.')
        return redirect('scheduler:busy_list')
    return render(request, 'shared/form.html', {'form': form, 'title': 'Chỉnh lịch bận' if pk else 'Thêm lịch bận / ca làm', 'back_url': 'scheduler:busy_list'})


@login_required
@transaction.atomic
def block_edit(request, pk=None):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    item = get_object_or_404(ScheduleBlock, pk=pk, user=request.user) if pk else None
    old_task = item.task if item else None
    form = BlockForm(request.POST if request.method == 'POST' else None, instance=item, user=request.user)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        for task in (old_task, item.task):
            if task:
                refresh_scheduled(task)
        messages.success(request, 'Đã lưu khung học.')
        return redirect('scheduler:calendar')
    return render(request, 'shared/form.html', {'form': form, 'title': 'Chỉnh khung học' if pk else 'Thêm khung học', 'back_url': 'scheduler:calendar', 'delete_url': f'/scheduler/block/{pk}/delete/' if pk else ''})


@login_required
def item_delete(request, pk, kind):
    model = BusyPeriod if kind == 'busy' else ScheduleBlock
    item = get_object_or_404(model, pk=pk, user=request.user)
    back = 'scheduler:busy_list' if kind == 'busy' else 'scheduler:calendar'
    if request.method == 'POST':
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            task = item.task if kind == 'block' else None
            item.delete()
            if task:
                refresh_scheduled(task)
        messages.success(request, 'Đã xóa mục lịch.')
        return redirect(back)
    return render(request, 'shared/delete.html', {'item': item, 'back_url': back})
