"""Kiểm tra danh sách bảng của database hiện tại (hỗ trợ cả SQLite lẫn PostgreSQL)."""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studyflow.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    table_names = connection.introspection.table_names(cursor)

for name in sorted(table_names):
    print(name)
