from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'code', 'color', 'credits', 'instructor', 'semester', 'description', 'is_active']
        widgets = {
            'color': forms.Select(attrs={'class': 'color-picker-select'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

@login_required
def course_list(request):
    """Danh sách & tạo môn học. Route: /courses/"""
    courses = Course.objects.filter(user=request.user)
    return render(request, 'courses/course_list.html', {'courses': courses})

@login_required
def course_create(request):
    if request.method == 'POST':
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.user = request.user
            course.save()
            messages.success(request, f'Đã thêm môn học "{course.name}" thành công!')
            return redirect('courses:list')
    else:
        form = CourseForm()
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Thêm môn học'})

@login_required
def course_update(request, pk):
    course = get_object_or_404(Course, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, f'Cập nhật môn học "{course.name}" thành công!')
            return redirect('courses:list')
    else:
        form = CourseForm(instance=course)
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Chỉnh sửa môn học', 'course': course})

@login_required
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk, user=request.user)
    if request.method == 'POST':
        course_name = course.name
        course.delete()
        messages.success(request, f'Đã xóa môn học "{course_name}".')
        return redirect('courses:list')
    return render(request, 'courses/course_confirm_delete.html', {'course': course})
