from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from .views import CustomLoginView, CustomLogoutView, register, profile

app_name = 'accounts'

urlpatterns = [
    path('password/change/', auth_views.PasswordChangeView.as_view(template_name='accounts/password_form.html', success_url=reverse_lazy('accounts:password_change_done')), name='password_change'),
    path('password/change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='accounts/password_done.html'), name='password_change_done'),
    path('password/reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_form.html', email_template_name='accounts/password_reset_email.txt', subject_template_name='accounts/password_reset_subject.txt', success_url=reverse_lazy('accounts:password_reset_done')), name='password_reset'),
    path('password/reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('password/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_form.html', success_url=reverse_lazy('accounts:password_reset_complete')), name='password_reset_confirm'),
    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_done.html'), name='password_reset_complete'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'),
    path('register/', register, name='register'),
    path('profile/', profile, name='profile'),
]
