from django.db import models
from django.conf import settings

class Course(models.Model):
    """
    Quản lý môn học của sinh viên.
    Mỗi môn học có màu đại diện để hiển thị trên Calendar và Dashboard.
    """
    COLOR_CHOICES = [
        ('#3B82F6', 'Xanh lam (Blue)'),
        ('#10B981', 'Xanh lá (Green)'),
        ('#F59E0B', 'Vàng hổ phách (Amber)'),
        ('#EF4444', 'Đỏ (Red)'),
        ('#8B5CF6', 'Tím (Purple)'),
        ('#EC4899', 'Hồng (Pink)'),
        ('#06B6D4', 'Xanh lơ (Cyan)'),
        ('#6B7280', 'Xám (Gray)'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name='Người dùng'
    )
    name = models.CharField('Tên môn học', max_length=150)
    code = models.CharField('Mã môn học', max_length=30, blank=True)
    color = models.CharField('Màu sắc', max_length=20, choices=COLOR_CHOICES, default='#3B82F6')
    credits = models.PositiveSmallIntegerField('Số tín chỉ', default=3)
    instructor = models.CharField('Giảng viên', max_length=100, blank=True)
    semester = models.CharField('Học kỳ', max_length=50, default='Học kỳ 1')
    description = models.TextField('Mô tả', blank=True)
    is_active = models.BooleanField('Đang học', default=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    class Meta:
        verbose_name = 'Môn học'
        verbose_name_plural = 'Danh sách môn học'
        ordering = ['name']

    def __str__(self):
        return f"{self.code} - {self.name}" if self.code else self.name
