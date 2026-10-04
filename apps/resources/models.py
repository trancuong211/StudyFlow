import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def resource_path(instance, filename):
    return f"resources/{instance.user_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class StudyResource(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_resources",
    )
    course = models.ForeignKey(
        "courses.Course", null=True, blank=True, on_delete=models.SET_NULL
    )
    task = models.ForeignKey(
        "tasks.Task", null=True, blank=True, on_delete=models.SET_NULL
    )
    title = models.CharField("Tên tài liệu", max_length=200)
    description = models.TextField("Ghi chú ôn tập", blank=True)
    url = models.URLField("Link tài liệu", blank=True, max_length=1000)
    file = models.FileField(
        "Tệp tài liệu (tối đa 10 MB)", upload_to=resource_path, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        if bool(self.url) == bool(self.file):
            raise ValidationError("Chọn một link hoặc một tệp tài liệu.")
        if self.url and not self.url.startswith(("https://", "http://")):
            raise ValidationError("Link cần bắt đầu bằng https:// hoặc http://.")
        for name in ("course", "task"):
            item = getattr(self, name)
            if item and item.user_id != self.user_id:
                raise ValidationError(
                    "Môn học/công việc không thuộc tài khoản của bạn."
                )
