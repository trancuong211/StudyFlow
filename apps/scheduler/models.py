from django.db import models
from django.conf import settings
from apps.tasks.models import Task

class ScheduleBlock(models.Model):
    """
    Block thời gian học tập / làm việc cụ thể được sắp xếp trên Calendar.
    Hỗ trợ cả block sinh ra tự động bởi thuật toán và block thủ công.
    is_locked = True để thuật toán không tự ý ghi đè/xóa khi chạy lại lịch.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedule_blocks',
        verbose_name='Người dùng'
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='schedule_blocks',
        verbose_name='Công việc liên kết'
    )
    title = models.CharField('Tiêu đề block', max_length=200)
    start_time = models.DateTimeField('Thời gian bắt đầu')
    end_time = models.DateTimeField('Thời gian kết thúc')
    is_auto_generated = models.BooleanField('Tự động tạo bởi AI/Thuật toán', default=False)
    is_locked = models.BooleanField(
        'Đã khóa (không ghi đè)',
        default=False,
        help_text='Khóa block để thuật toán sắp lịch tự động không dịch chuyển thời gian'
    )
    notes = models.TextField('Ghi chú thêm', blank=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    class Meta:
        verbose_name = 'Block lịch'
        verbose_name_plural = 'Danh sách Block lịch'
        ordering = ['start_time']

    def __str__(self):
        lock_status = "🔒" if self.is_locked else ""
        return f"{lock_status} {self.title} ({self.start_time.strftime('%H:%M %d/%m')} - {self.end_time.strftime('%H:%M %d/%m')})"

    @property
    def duration_minutes(self):
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
