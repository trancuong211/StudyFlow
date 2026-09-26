import json
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import ScheduleBlock
from .engine.optimizer import ScheduleOptimizer

@login_required
def calendar_view(request):
    """Giao diện lịch chính dạng tuần/tháng với FullCalendar."""
    return render(request, 'scheduler/calendar.html')

@login_required
def api_events(request):
    """API cung cấp danh sách sự kiện cho FullCalendar (hỗ trợ màu môn học, trạng thái lock)."""
    blocks = ScheduleBlock.objects.filter(user=request.user).select_related('task', 'task__course')
    events = []

    for b in blocks:
        color = '#3B82F6'
        if b.task and b.task.course:
            color = b.task.course.color

        events.append({
            'id': b.id,
            'title': b.title,
            'start': b.start_time.isoformat(),
            'end': b.end_time.isoformat(),
            'backgroundColor': color,
            'borderColor': '#1E3A8A' if b.is_locked else color,
            'textColor': '#FFFFFF',
            'extendedProps': {
                'taskId': b.task_id,
                'isLocked': b.is_locked,
                'isAuto': b.is_auto_generated,
                'notes': b.notes,
            }
        })

    return JsonResponse(events, safe=False)

@login_required
@require_POST
def api_update_block(request, pk):
    """Cập nhật thời gian khi kéo thả (drag & drop) hoặc resize block trên lịch."""
    block = get_object_or_404(ScheduleBlock, pk=pk, user=request.user)
    try:
        data = json.loads(request.body)
        if 'start' in data:
            block.start_time = datetime.fromisoformat(data['start'])
        if 'end' in data:
            block.end_time = datetime.fromisoformat(data['end'])
        
        # Khi người dùng tự tay chỉnh sửa lịch, tự động khóa block để không bị thuật toán ghi đè
        if data.get('lock_on_edit', True):
            block.is_locked = True

        block.save()
        return JsonResponse({'status': 'success', 'is_locked': block.is_locked})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@require_POST
def api_toggle_lock(request, pk):
    """Bật/tắt trạng thái khóa của một block lịch."""
    block = get_object_or_404(ScheduleBlock, pk=pk, user=request.user)
    block.is_locked = not block.is_locked
    block.save(update_fields=['is_locked'])
    return JsonResponse({'status': 'success', 'is_locked': block.is_locked})

@login_required
def trigger_auto_schedule(request):
    """Kích hoạt thuật toán tự động sắp xếp lịch."""
    optimizer = ScheduleOptimizer(user=request.user)
    created_blocks = optimizer.run()
    messages.success(request, f'Đã tự động sắp xếp {len(created_blocks)} khung giờ học vào lịch!')
    return redirect('scheduler:calendar')
