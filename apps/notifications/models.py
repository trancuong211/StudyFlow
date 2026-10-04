from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    task = models.ForeignKey(
        "tasks.Task", null=True, blank=True, on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    dedup_key = models.CharField(max_length=200, unique=True)
    is_read = models.BooleanField(default=False)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
