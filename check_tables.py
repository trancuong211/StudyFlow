import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studyflow.settings')
sys.path.insert(0, 'C:/WEBLTPY')
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
for row in cursor.fetchall():
    print(row)