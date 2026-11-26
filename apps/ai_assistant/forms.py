from django import forms

from .models import AIConfiguration

INPUT_CLASS = (
    'w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 '
    'placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-2 '
    'focus:ring-brand-100 transition-colors'
)


class AIConfigurationForm(forms.ModelForm):
    api_key = forms.CharField(
        label='API key',
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'class': INPUT_CLASS,
                'autocomplete': 'new-password',
                'placeholder': 'sk-...',
            }
        ),
        help_text='Để trống để giữ API key đang lưu.'
    )
    remove_api_key = forms.BooleanField(
        label='Xóa API key đang lưu',
        required=False
    )

    class Meta:
        model = AIConfiguration
        fields = ('provider', 'model_name', 'base_url', 'is_active')
        widgets = {
            'provider': forms.Select(attrs={'class': INPUT_CLASS}),
            'model_name': forms.HiddenInput(),
            'base_url': forms.URLInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'https://openrouter.ai/api/v1',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.has_api_key:
            self.fields['api_key'].help_text = (
                f'Đang lưu key {self.instance.key_hint}. '
                'Để trống để giữ nguyên hoặc nhập key mới để thay thế.'
            )

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get('provider')
        if provider == AIConfiguration.Provider.CUSTOM:
            if not cleaned.get('base_url'):
                self.add_error('base_url', 'Base URL là bắt buộc với nhà cung cấp tùy chỉnh.')
            if not cleaned.get('model_name'):
                self.add_error('model_name', 'Vui lòng chọn model cho nhà cung cấp tùy chỉnh.')
        return cleaned

    def save(self, commit=True):
        config = super().save(commit=False)
        if self.cleaned_data.get('remove_api_key'):
            config.set_api_key('')
        else:
            raw_key = self.cleaned_data.get('api_key')
            if raw_key:
                config.set_api_key(raw_key)
        if commit:
            config.save()
        return config
