from pathlib import Path

from django import forms
from django.urls import reverse

from apps.courses.models import Course
from apps.tasks.models import Task

from .models import StudyResource


class PrivateResourceFileInput(forms.ClearableFileInput):
    template_name = "resources/widgets/private_file_input.html"
    download_url = None

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["download_url"] = self.download_url
        return context


class ResourceForm(forms.ModelForm):
    class Meta:
        model = StudyResource
        fields = ["title", "course", "task", "description", "url", "file"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "file": PrivateResourceFileInput(),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        self.fields["course"].queryset = Course.objects.filter(user=user)
        self.fields["task"].queryset = Task.objects.filter(user=user)
        if self.instance.pk:
            self.fields["file"].widget.download_url = reverse(
                "resources:download", args=[self.instance.pk]
            )

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("Tệp vượt quá 10 MB.")
            if Path(file.name).suffix.lower() not in {
                ".pdf",
                ".doc",
                ".docx",
                ".ppt",
                ".pptx",
                ".xls",
                ".xlsx",
                ".txt",
                ".md",
                ".csv",
                ".png",
                ".jpg",
                ".jpeg",
            }:
                raise forms.ValidationError(
                    "Chọn PDF, Office, văn bản hoặc ảnh PNG/JPG."
                )
        return file
