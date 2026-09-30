from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.courses.models import Course

class Task(models.Model):
    """
    Quản lý công việc, bài tập, kỳ thi và deadline của sinh viên.
    Trọng tâm chứa dữ liệu ưu tiên và thời lượng ước tính để thuật toán lập lịch sử dụng.
    """
    class Priority(models.IntegerChoices):
        LOW = 1, 'Thấp'
        MEDIUM = 2, 'Trung bình'
        HIGH = 3, 'Cao'
        URGENT = 4, 'Khẩn cấp'

    class Status(models.TextChoices):
        TODO = 'TODO', 'Cần làm'
        IN_PROGRESS = 'IN_PROGRESS', 'Đang làm'
        COMPLETED = 'COMPLETED', 'Đã hoàn thành'

    class Difficulty(models.IntegerChoices):
        EASY = 1, 'Dễ'
        MEDIUM = 2, 'Trung bình'
        HARD = 3, 'Khó / Nặng não'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='Người dùng'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='Môn học'
    )
    title = models.CharField('Tiêu đề công việc', max_length=200)
    description = models.TextField('Chi tiết công việc', blank=True)
    priority = models.IntegerField('Độ ưu tiên', choices=Priority.choices, default=Priority.MEDIUM)
    estimated_duration = models.PositiveIntegerField(
        'Thời lượng ước tính (phút)', default=60, help_text='Ước tính số phút cần để hoàn thành'
    )
    deadline = models.DateTimeField('Thời hạn (Deadline)')
    status = models.CharField('Trạng thái', max_length=20, choices=Status.choices, default=Status.TODO)
    difficulty = models.IntegerField('Độ khó', choices=Difficulty.choices, default=Difficulty.MEDIUM)
    
    # Tracking fields
    is_scheduled = models.BooleanField('Đã xếp vào lịch', default=False)
    completed_at = models.DateTimeField('Thời điểm hoàn thành', null=True, blank=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    class Meta:
        verbose_name = 'Công việc / Deadline'
        verbose_name_plural = 'Danh sách công việc & Deadline'
        ordering = ['deadline', '-priority']

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"

    @property
    def is_overdue(self):
        return self.status != self.Status.COMPLETED and self.deadline < timezone.now()

    def mark_completed(self):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        """Đồng bộ completed_at theo trạng thái: COMPLETED -> có timestamp, ngược lại -> None."""
        if self.status == self.Status.COMPLETED:
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
        super().save(*args, **kwargs)
