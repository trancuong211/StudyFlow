from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ResourceForm
from .models import StudyResource


@login_required
def resource_list(request):
    items = StudyResource.objects.filter(user=request.user).select_related(
        "course", "task"
    )
    query = request.GET.get("q", "").strip()[:200]
    if query:
        items = items.filter(title__icontains=query)
    return render(request, "resources/list.html", {"resources": items, "query": query})


@login_required
@transaction.atomic
def resource_edit(request, pk=None):
    item = get_object_or_404(StudyResource, pk=pk, user=request.user) if pk else None
    old_name = item.file.name if item and item.file else None
    form = ResourceForm(
        request.POST if request.method == "POST" else None,
        request.FILES or None,
        instance=item,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        if old_name and saved.file.name != old_name:
            storage = saved.file.storage
            transaction.on_commit(lambda: storage.delete(old_name))
        messages.success(request, "Đã lưu tài liệu ôn tập.")
        return redirect("resources:list")
    return render(
        request,
        "shared/form.html",
        {
            "form": form,
            "title": "Chỉnh sửa tài liệu" if pk else "Thêm tài liệu ôn tập",
            "back_url": "resources:list",
            "multipart": True,
        },
    )


@login_required
def resource_download(request, pk):
    item = get_object_or_404(StudyResource, pk=pk, user=request.user)
    if not item.file:
        raise Http404
    try:
        return FileResponse(
            item.file.open("rb"),
            as_attachment=True,
            filename=item.title + Path(item.file.name).suffix,
        )
    except FileNotFoundError:
        raise Http404("Tệp không còn tồn tại.")


@login_required
def resource_delete(request, pk):
    item = get_object_or_404(StudyResource, pk=pk, user=request.user)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Đã xóa tài liệu.")
        return redirect("resources:list")
    return render(
        request, "shared/delete.html", {"item": item, "back_url": "resources:list"}
    )
