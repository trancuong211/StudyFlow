from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.resources"
    verbose_name = "Tài liệu ôn tập"

    def ready(self):
        from . import signals  # noqa: F401
