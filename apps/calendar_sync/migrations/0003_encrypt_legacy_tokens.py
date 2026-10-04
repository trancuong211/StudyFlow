from django.db import migrations


def encrypt_tokens(apps, schema_editor):
    Token = apps.get_model("calendar_sync", "GoogleCalendarToken")
    for token in Token.objects.iterator():
        # EncryptedTextField reads old plaintext and encrypts on save.
        token.save(update_fields=["access_token", "refresh_token", "client_secret"])


class Migration(migrations.Migration):
    dependencies = [("calendar_sync", "0002_googlecalendartoken_expiry_and_more")]
    operations = [migrations.RunPython(encrypt_tokens, migrations.RunPython.noop)]
