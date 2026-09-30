from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import unicodedata
from .models import Task
from apps.courses.models import Course

class TaskForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
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

@login_required
def task_list(request):
    """Danh sách task, lọc theo trạng thái & ưu tiên. Route: /tasks/"""
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    course_filter = request.GET.get('course')

    tasks = Task.objects.filter(user=request.user)

    # Chỉ áp dụng bộ lọc khi tham số hợp lệ, giá trị sai thì bỏ qua (không lỗi 500)
    if status_filter in Task.Status.values:
        tasks = tasks.filter(status=status_filter)
    if priority_filter and priority_filter.isdigit() and int(priority_filter) in Task.Priority.values:
        tasks = tasks.filter(priority=int(priority_filter))
    if course_filter and course_filter.isdigit():
        tasks = tasks.filter(course_id=int(course_filter))

    return render(request, 'tasks/task_list.html', {
        'tasks': tasks,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'course_filter': course_filter,
    })

@login_required
def task_create(request):
    if request.method == 'POST':
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.course = form.resolve_course()
            task.save()
            messages.success(request, f'Đã thêm công việc "{task.title}" thành công!')
            return redirect('tasks:list')
    else:
        form = TaskForm(user=request.user)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Thêm công việc / Deadline'})

@login_required
def task_update(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.course = form.resolve_course()
            task.save()
            messages.success(request, f'Cập nhật "{task.title}" thành công!')
            return redirect('tasks:list')
    else:
        form = TaskForm(instance=task, user=request.user)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Chỉnh sửa công việc', 'task': task})

@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        title = task.title
        task.delete()
        messages.success(request, f'Đã xóa công việc "{title}".')
        return redirect('tasks:list')
    return render(request, 'tasks/task_confirm_delete.html', {'task': task})

@login_required
@require_POST
def task_toggle_status(request, pk):
    """Đánh dấu hoàn thành / chưa hoàn thành công việc."""
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
