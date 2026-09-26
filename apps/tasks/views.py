from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Task
from apps.courses.models import Course

class TaskForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label='Hạn chót (Deadline)'
    )

    class Meta:
        model = Task
        fields = [
            'course', 'title', 'description', 'priority',
            'estimated_duration', 'deadline', 'status', 'difficulty'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['course'].queryset = Course.objects.filter(user=user, is_active=True)

@login_required
def task_list(request):
    """Danh sách task, lọc theo trạng thái & ưu tiên. Route: /tasks/"""
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    course_filter = request.GET.get('course')

    tasks = Task.objects.filter(user=request.user)

    if status_filter:
        tasks = tasks.filter(status=status_filter)
    if priority_filter:
        tasks = tasks.filter(priority=priority_filter)
    if course_filter:
        tasks = tasks.filter(course_id=course_filter)

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
            form.save()
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
def task_toggle_status(request, pk):
    """Đánh dấu hoàn thành / chưa hoàn thành công việc."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if task.status == Task.Status.COMPLETED:
        task.status = Task.Status.TODO
        task.completed_at = None
    else:
        task.mark_completed()
    task.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'new_status': task.status})
    return redirect('tasks:list')
