from django.db import models
from django.conf import settings
from apps.tasks.models import Task

class PomodoroSession(models.Model):
    """
    Ghi nhận phiên tập trung Pomodoro của người dùng, liên kết với task đang học.
    """
    class SessionType(models.TextChoices):
        WORK = 'WORK', 'Làm việc / Học tập (25m)'
        SHORT_BREAK = 'SHORT_BREAK', 'Nghỉ ngắn (5m)'
        LONG_BREAK = 'LONG_BREAK', 'Nghỉ dài (15m)'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pomodoro_sessions',
        verbose_name='Người dùng'
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pomodoro_sessions',
        verbose_name='Công việc thực hiện'
    )
    session_type = models.CharField(
        'Loại phiên',
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.WORK
    )
    duration_minutes = models.PositiveIntegerField('Thời lượng (phút)', default=25)
    start_time = models.DateTimeField('Bắt đầu')
    end_time = models.DateTimeField('Kết thúc', null=True, blank=True)
    completed = models.BooleanField('Hoàn thành trọn vẹn', default=True)
    notes = models.CharField('Ghi chú phiên', max_length=255, blank=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'Phiên Pomodoro'
        verbose_name_plural = 'Danh sách phiên Pomodoro'
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.user.username} - {self.get_session_type_display()} ({self.duration_minutes}m)"
