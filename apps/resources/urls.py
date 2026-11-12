from django.urls import path

from . import views

app_name = "resources"
urlpatterns = [
    path("", views.resource_list, name="list"),
    path("new/", views.resource_edit, name="create"),
    path("<int:pk>/edit/", views.resource_edit, name="edit"),
    path("<int:pk>/download/", views.resource_download, name="download"),
    path("<int:pk>/delete/", views.resource_delete, name="delete"),
]
