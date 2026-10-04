from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import F, Q
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
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='schedule_end_after_start')]

    def __str__(self):
        lock_status = "🔒" if self.is_locked else ""
        return f"{lock_status} {self.title} ({self.start_time.strftime('%H:%M %d/%m')} - {self.end_time.strftime('%H:%M %d/%m')})"

    @property
    def duration_minutes(self):
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    def clean(self):
        if not self.start_time or not self.end_time:
            return
        if self.end_time <= self.start_time:
            raise ValidationError('Thời gian kết thúc phải sau thời gian bắt đầu.')
        if self.task_id:
            if self.task.user_id != self.user_id:
                raise ValidationError('Công việc không thuộc tài khoản của bạn.')
            if self.task.status == Task.Status.COMPLETED:
                raise ValidationError('Công việc này đã hoàn thành.')
            if self.end_time > self.task.deadline:
                raise ValidationError('Khung học kết thúc sau deadline của công việc.')
        if ScheduleBlock.objects.filter(user_id=self.user_id, start_time__lt=self.end_time,
                                        end_time__gt=self.start_time).exclude(pk=self.pk).exists():
            raise ValidationError('Khung giờ trùng với một lịch đã có. Hãy chọn giờ khác.')
        from .availability import busy_intervals
        if busy_intervals(self.user, self.start_time, self.end_time):
            raise ValidationError('Khung giờ trùng lịch bận hoặc sự kiện Google Calendar.')


class BusyPeriod(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='busy_periods')
    title = models.CharField('Hoạt động / ca làm', max_length=200)
    start_time = models.DateTimeField('Bắt đầu')
    end_time = models.DateTimeField('Kết thúc')
    repeats_weekly = models.BooleanField('Lặp lại hằng tuần', default=False)
    repeat_until = models.DateField('Lặp đến ngày (để trống = không giới hạn)', null=True, blank=True)
    notes = models.TextField('Ghi chú', blank=True)

    class Meta:
        ordering = ['start_time']
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='busy_end_after_start')]

    def __str__(self):
        return self.title

    def clean(self):
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError('Thời gian kết thúc phải sau thời gian bắt đầu.')
            if self.repeats_weekly and (self.end_time - self.start_time).total_seconds() >= 7 * 86400:
                raise ValidationError('Một lịch lặp cần ngắn hơn 7 ngày.')
            if self.repeat_until and self.repeat_until < self.start_time.date():
                raise ValidationError('Ngày kết thúc lặp phải từ ngày bắt đầu trở đi.')
