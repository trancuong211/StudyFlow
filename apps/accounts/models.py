from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class User(AbstractUser):
    """
    Custom User Model cho StudyFlow.
    Đăng nhập bằng username hoặc email, hỗ trợ cấu hình múi giờ và mục tiêu học tập.
    """
    email = models.EmailField('Địa chỉ Email', unique=True)
    full_name = models.CharField('Họ và tên', max_length=150, blank=True)
    timezone = models.CharField('Múi giờ', max_length=64, default='Asia/Ho_Chi_Minh')
    daily_study_goal_hours = models.PositiveSmallIntegerField(
        'Mục tiêu học mỗi ngày (giờ)', default=4, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    is_google_connected = models.BooleanField('Đã kết nối Google Calendar', default=False)
    study_start_hour = models.PositiveSmallIntegerField('Giờ bắt đầu học', default=8, validators=[MaxValueValidator(22)])
    study_end_hour = models.PositiveSmallIntegerField('Giờ kết thúc học', default=22, validators=[MinValueValidator(1), MaxValueValidator(23)])
    email_reminders = models.BooleanField('Nhắc deadline qua email', default=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    def __str__(self):
        return self.full_name or self.username or self.email

    def clean(self):
        super().clean()
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError({'timezone': 'Múi giờ không hợp lệ.'})
        if self.study_start_hour is not None and self.study_end_hour is not None and self.study_start_hour >= self.study_end_hour:
            raise ValidationError('Giờ kết thúc học phải sau giờ bắt đầu.')
