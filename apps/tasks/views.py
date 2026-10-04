from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import unicodedata
from .models import Task
from apps.courses.models import Course
from apps.scheduler.progress import refresh_scheduled, planned_minutes, remaining_minutes

class TaskForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        label='Hạn chót (Deadline)'
    )
    # Tự nhập tên môn học thay vì chọn từ dropdown
    course_name = forms.CharField(
        label='Môn học',
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'VD: Đại số, Xử lý tín hiệu, Tiếng Anh...'}),
        help_text='Nhập tên môn học. Nếu chưa có, hệ thống sẽ tự tạo môn mới cho bạn.',
    )

    class Meta:
        model = Task
        fields = [
            'title', 'description', 'priority',
            'estimated_duration', 'deadline', 'status', 'difficulty'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Khi sửa task, điền sẵn tên môn học hiện tại
        if not self.is_bound and self.instance and self.instance.course_id:
            self.fields['course_name'].initial = self.instance.course.name

    @staticmethod
    def _normalize(name):
        """Chuẩn hóa tên môn để so khớp không phân biệt hoa/thường (hỗ trợ tiếng Việt)."""
        return unicodedata.normalize('NFC', name).strip().casefold()

    def resolve_course(self):
        """Tìm môn học theo tên vừa nhập (không phân biệt hoa thường), chưa có thì tạo mới."""
        name = (self.cleaned_data.get('course_name') or '').strip()
        if not name or self.user is None:
            return None
        target = self._normalize(name)
        course = next(
            (c for c in Course.objects.filter(user=self.user) if self._normalize(c.name) == target),
            None
        )
        if course is None:
            course = Course.objects.create(user=self.user, name=name)
        return course

    def clean(self):
        data = super().clean()
        deadline = data.get('deadline')
        if self.instance.pk and deadline and data.get('status') != Task.Status.COMPLETED:
            preserved = self.instance.schedule_blocks.filter(
                Q(is_locked=True) | Q(is_auto_generated=False),
                end_time__gt=deadline,
            )
            if preserved.exists():
                raise forms.ValidationError('Có khung học thủ công hoặc đã khóa sau deadline mới. Hãy chỉnh khung học trước.')
        return data

@login_required
def task_list(request):
    """Danh sách task, lọc theo trạng thái & ưu tiên. Route: /tasks/"""
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    course_filter = request.GET.get('course')

    tasks = Task.objects.filter(user=request.user).select_related('course')

    # Chỉ áp dụng bộ lọc khi tham số hợp lệ, giá trị sai thì bỏ qua (không lỗi 500)
    if status_filter in Task.Status.values:
        tasks = tasks.filter(status=status_filter)
    else:
        status_filter = None
    if priority_filter in {str(value) for value in Task.Priority.values}:
        tasks = tasks.filter(priority=int(priority_filter))
    else:
        priority_filter = None
    if (course_filter and len(course_filter) <= 19 and course_filter.isascii()
            and course_filter.isdigit() and 0 < int(course_filter) <= 2**63 - 1):
        tasks = tasks.filter(course_id=int(course_filter))
        course_filter = str(int(course_filter))
    else:
        course_filter = None

    query = request.GET.get('q', '').strip()[:200]
    if query:
        tasks = tasks.filter(title__icontains=query)
    tasks = list(tasks)
    for task in tasks:
        task.is_scheduled = task.status != Task.Status.COMPLETED and planned_minutes(task) >= remaining_minutes(task)
    return render(request, 'tasks/task_list.html', {
        'tasks': tasks,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'course_filter': course_filter,
        'query': query,
        'courses': Course.objects.filter(user=request.user),
    })

@login_required
@transaction.atomic
def task_create(request):
    if request.method == 'POST':
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.course = form.resolve_course()
            task.save()
            refresh_scheduled(task)
            messages.success(request, f'Đã thêm công việc "{task.title}" thành công!')
            return redirect('tasks:list')
    else:
        form = TaskForm(user=request.user)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Thêm công việc / Deadline'})

@login_required
@transaction.atomic
def task_update(request, pk):
    if request.method == 'POST':
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.course = form.resolve_course()
            task.save()
            task.schedule_blocks.filter(is_auto_generated=True, is_locked=False, end_time__gt=task.deadline).delete()
            refresh_scheduled(task)
            messages.success(request, f'Cập nhật "{task.title}" thành công!')
            return redirect('tasks:list')
    else:
        form = TaskForm(instance=task, user=request.user)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Chỉnh sửa công việc', 'task': task})

@login_required
@transaction.atomic
def task_delete(request, pk):
    if request.method == 'POST':
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        title = task.title
        task.delete()
        messages.success(request, f'Đã xóa công việc "{title}".')
        return redirect('tasks:list')
    return render(request, 'tasks/task_confirm_delete.html', {'task': task})

@login_required
@require_POST
@transaction.atomic
def task_toggle_status(request, pk):
    """Đánh dấu hoàn thành / chưa hoàn thành công việc."""
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if task.status == Task.Status.COMPLETED:
        task.status = Task.Status.TODO
        task.completed_at = None
        task.save()
    else:
        task.mark_completed()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'new_status': task.status})
    return redirect('tasks:list')
