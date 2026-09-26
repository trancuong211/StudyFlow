from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Custom User Model cho StudyFlow.
    Đăng nhập bằng username hoặc email, hỗ trợ cấu hình múi giờ và mục tiêu học tập.
    """
    email = models.EmailField('Địa chỉ Email', unique=True)
    full_name = models.CharField('Họ và tên', max_length=150, blank=True)
    timezone = models.CharField('Múi giờ', max_length=64, default='Asia/Ho_Chi_Minh')
    daily_study_goal_hours = models.PositiveSmallIntegerField(
        'Mục tiêu học mỗi ngày (giờ)', default=4
    )
    is_google_connected = models.BooleanField('Đã kết nối Google Calendar', default=False)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    def __str__(self):
        return self.full_name or self.username or self.email
