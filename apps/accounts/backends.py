from django.contrib.auth.backends import ModelBackend

from .models import User


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.filter(email__iexact=username).first()
        if user is None:
            User().set_password(password)
        elif user.check_password(password) and self.user_can_authenticate(user):
            return user
