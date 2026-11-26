from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    return render(
        request,
        "notifications/list.html",
        {"notifications": Notification.objects.filter(user=request.user)[:100]},
    )


@login_required
@require_POST
def mark_read(request, pk):
    item = get_object_or_404(Notification, user=request.user, pk=pk)
    item.is_read = True
    item.save(update_fields=["is_read"])
    return redirect("notifications:list")
