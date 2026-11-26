from django.db import migrations, models

COLUMNS = {
    'email_reminders': 'boolean NOT NULL DEFAULT TRUE',
    'study_start_hour': 'smallint NOT NULL DEFAULT 8',
    'study_end_hour': 'smallint NOT NULL DEFAULT 22',
}


def _existing_columns(connection, table):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }


def add_missing_columns(apps, schema_editor):
    """Thêm cột còn thiếu, bỏ qua nếu DB đã có (DB cũ được migrate bởi phiên bản khác)."""
    connection = schema_editor.connection
    table = 'accounts_user'
    existing = _existing_columns(connection, table)
    for name, definition in COLUMNS.items():
        if name not in existing:
            schema_editor.execute(
                f'ALTER TABLE {schema_editor.quote_name(table)} '
                f'ADD COLUMN {schema_editor.quote_name(name)} {definition}'
            )


def remove_columns(apps, schema_editor):
    connection = schema_editor.connection
    table = 'accounts_user'
    existing = _existing_columns(connection, table)
    for name in COLUMNS:
        if name in existing:
            schema_editor.execute(
                f'ALTER TABLE {schema_editor.quote_name(table)} '
                f'DROP COLUMN {schema_editor.quote_name(name)}'
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_daily_study_goal_hours_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(add_missing_columns, remove_columns),
            ],
        ),
    ]
