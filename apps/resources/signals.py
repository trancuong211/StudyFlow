from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import StudyResource


@receiver(post_delete, sender=StudyResource)
def delete_owned_file(sender, instance, **kwargs):
    if instance.file:
        name, storage = instance.file.name, instance.file.storage
        transaction.on_commit(lambda: storage.delete(name))
