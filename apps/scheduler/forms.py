from django import forms
from django.core.exceptions import ValidationError

from .availability import recurring_intervals
from .models import BusyPeriod, ScheduleBlock


class BusyPeriodForm(forms.ModelForm):
    class Meta:
        model = BusyPeriod
        fields = [
            "title",
            "start_time",
            "end_time",
            "repeats_weekly",
            "repeat_until",
            "notes",
        ]
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "repeat_until": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user

    def clean(self):
        data = super().clean()
        if data.get("start_time") and data.get("end_time"):
            for field in ("start_time", "end_time", "repeats_weekly", "repeat_until"):
                setattr(self.instance, field, data.get(field))
            if self.instance.end_time > self.instance.start_time:
                for block in ScheduleBlock.objects.filter(
                    user=self.instance.user, end_time__gt=self.instance.start_time
                ):
                    if recurring_intervals(
                        self.instance, block.start_time, block.end_time
                    ):
                        raise ValidationError(
                            f'Lịch bận trùng "{block.title}". Hãy chỉnh hoặc xóa khung học đó trước.'
                        )
        return data


class BlockForm(forms.ModelForm):
    class Meta:
        model = ScheduleBlock
        fields = ["title", "task", "start_time", "end_time", "notes", "is_locked"]
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        from apps.tasks.models import Task

        super().__init__(*args, **kwargs)
        self.instance.user = user
        self.fields["task"].queryset = Task.objects.filter(user=user).exclude(
            status="COMPLETED"
        )
        if not self.instance.pk:
            self.fields["is_locked"].initial = True
