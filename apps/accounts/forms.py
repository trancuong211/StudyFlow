from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class StudyPreferencesMixin:
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Email đã được sử dụng.')
        return email

    def clean_timezone(self):
        value = self.cleaned_data['timezone']
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise forms.ValidationError('Múi giờ không hợp lệ. Ví dụ: Asia/Ho_Chi_Minh.')
        return value

    def clean_daily_study_goal_hours(self):
        value = self.cleaned_data['daily_study_goal_hours']
        if not 1 <= value <= 12:
            raise forms.ValidationError('Mục tiêu học cần từ 1 đến 12 giờ/ngày.')
        return value


class CustomUserCreationForm(StudyPreferencesMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'timezone', 'daily_study_goal_hours')


class CustomUserChangeForm(StudyPreferencesMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'timezone', 'daily_study_goal_hours',
                  'study_start_hour', 'study_end_hour', 'email_reminders')

    def clean(self):
        data = super().clean()
        start, end = data.get('study_start_hour'), data.get('study_end_hour')
        if start is not None and end is not None and not 0 <= start < end <= 23:
            raise forms.ValidationError('Giờ học cần nằm trong 0–23 và giờ kết thúc phải sau giờ bắt đầu.')
        return data
