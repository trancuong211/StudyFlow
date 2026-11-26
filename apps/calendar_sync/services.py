import hashlib
import json
import logging
import uuid
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

import httplib2
from django.db import transaction
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.accounts.timezones import user_zone
from apps.notifications.models import Notification
from apps.scheduler.models import ScheduleBlock

from .models import CalendarExport, GoogleCalendarEvent, GoogleCalendarToken

logger = logging.getLogger(__name__)


def calendar_client(token):
    expiry = (
        token.expiry.astimezone(dt_timezone.utc).replace(tzinfo=None)
        if token.expiry
        else None
    )
    credentials = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri=token.token_uri,
        client_id=token.client_id,
        client_secret=token.client_secret,
        scopes=token.scopes.split(),
        expiry=expiry,
    )
    if not credentials.valid:
        if not credentials.refresh_token:
            raise ValueError("Phiên Google đã hết hạn. Hãy kết nối lại tài khoản.")

        class BoundedRequest(Request):
            def __call__(self, *args, **kwargs):
                kwargs["timeout"] = 10
                return super().__call__(*args, **kwargs)

        credentials.refresh(BoundedRequest())
    token.access_token = credentials.token
    token.refresh_token = credentials.refresh_token or token.refresh_token
    token.expiry = (
        credentials.expiry.replace(tzinfo=dt_timezone.utc)
        if credentials.expiry
        else None
    )
    token.save(
        update_fields=["access_token", "refresh_token", "client_secret", "expiry"]
    )
    return build(
        "calendar",
        "v3",
        http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=10)),
        cache_discovery=False,
    )


def event_time(value, zone):
    if value.get("dateTime"):
        result = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=zone)
    return datetime.combine(
        datetime.fromisoformat(value["date"]).date(), time.min, zone
    )


def _import_events(user, items, start, end, zone):
    """Apply remote events in one short transaction (no network calls here)."""
    seen = []
    with transaction.atomic():
        for event in items:
            private = event.get("extendedProperties", {}).get("private", {})
            if (
                private.get("studyflow_owner") == str(user.pk)
                or event.get("status") == "cancelled"
            ):
                continue
            if not event.get("start") or not event.get("end"):
                continue
            a, b = event_time(event["start"], zone), event_time(event["end"], zone)
            if b <= a:
                continue
            seen.append(event["id"])
            GoogleCalendarEvent.objects.update_or_create(
                user=user,
                google_id=event["id"],
                defaults={
                    "title": event.get("summary", "Sự kiện Google")[:200],
                    "start_time": a,
                    "end_time": b,
                    "is_busy": event.get("transparency") != "transparent",
                },
            )
        GoogleCalendarEvent.objects.filter(
            user=user, start_time__lt=end, end_time__gt=start
        ).exclude(google_id__in=seen).delete()
    return seen


def _notify_google_conflicts(user, now, zone):
    """Create one notification per study block now overlapping a busy Google event."""
    events = list(
        GoogleCalendarEvent.objects.filter(
            user=user, end_time__gt=now, is_busy=True
        ).values_list("start_time", "end_time")
    )
    if not events:
        return 0
    created = 0
    blocks = ScheduleBlock.objects.filter(user=user, end_time__gt=now).only(
        "pk", "task_id", "title", "start_time", "end_time"
    )
    for block in blocks:
        if not any(a < block.end_time and b > block.start_time for a, b in events):
            continue
        local = timezone.localtime(block.start_time, zone).strftime("%H:%M %d/%m")
        _, made = Notification.objects.get_or_create(
            dedup_key=f"google-conflict:{block.pk}:{block.start_time.isoformat()}",
            defaults={
                "user": user,
                "task_id": block.task_id,
                "title": ("Khung học bị trùng lịch Google: " + block.title)[:200],
                "content": (
                    f'Khung "{block.title}" lúc {local} trùng sự kiện Google mới. '
                    "Hãy chỉnh khung hoặc chạy lại lập lịch tuần."
                ),
            },
        )
        created += int(made)
    return created


def _export_block(user, token, events_api, block, zone):
    """Create/update one Google event for a study block. Network errors propagate."""
    body = {
        "summary": block.title,
        "description": block.notes,
        "start": {"dateTime": block.start_time.isoformat(), "timeZone": str(zone)},
        "end": {"dateTime": block.end_time.isoformat(), "timeZone": str(zone)},
        "extendedProperties": {
            "private": {
                "studyflow_owner": str(user.pk),
                "studyflow_block": str(block.pk),
            }
        },
    }
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    mapping = CalendarExport.objects.filter(user=user, block=block).first()
    if mapping:
        try:
            remote = events_api.get(
                calendarId=token.calendar_id, eventId=mapping.google_id
            ).execute()
            if remote.get("status") == "cancelled":
                mapping.delete()
                mapping = None
            elif remote.get("extendedProperties", {}).get("private", {}).get(
                "studyflow_owner"
            ) != str(user.pk):
                raise ValueError(
                    "Sự kiện xuất không còn thuộc StudyFlow. Hãy kết nối lại lịch."
                )
            elif any(
                remote.get(k) != body[k]
                for k in ("summary", "description", "start", "end")
            ):
                events_api.patch(
                    calendarId=token.calendar_id,
                    eventId=mapping.google_id,
                    body=body,
                ).execute()
        except HttpError as exc:
            if exc.resp.status not in (404, 410):
                raise
            mapping.delete()
            mapping = None
    if not mapping:
        google_id = hashlib.sha256(
            f"studyflow:{user.pk}:{block.pk}".encode()
        ).hexdigest()
        try:
            result = events_api.insert(
                calendarId=token.calendar_id, body={**body, "id": google_id}
            ).execute()
        except HttpError as exc:
            if exc.resp.status != 409:
                raise
            remote = events_api.get(
                calendarId=token.calendar_id, eventId=google_id
            ).execute()
            if remote.get("status") == "cancelled":
                result = events_api.insert(
                    calendarId=token.calendar_id,
                    body={**body, "id": uuid.uuid4().hex},
                ).execute()
            elif remote.get("extendedProperties", {}).get("private", {}).get(
                "studyflow_owner"
            ) == str(user.pk):
                result = events_api.patch(
                    calendarId=token.calendar_id, eventId=google_id, body=body
                ).execute()
            else:
                raise ValueError(
                    "Không thể tạo sự kiện Google do ID trùng."
                ) from exc
        mapping = CalendarExport.objects.create(
            user=user, block=block, google_id=result["id"]
        )
    mapping.fingerprint = fingerprint
    mapping.save(update_fields=["fingerprint"])
    return mapping


def sync_calendar(user, client=None):
    """Sync Google Calendar without holding DB locks across network calls.

    Network work happens outside transactions; imports use one short transaction and
    each exported block is handled independently so one failure does not roll back the
    whole batch.
    """
    token = GoogleCalendarToken.objects.get(user=user)
    client = client or calendar_client(token)
    events_api = client.events()
    now = timezone.now()
    start, end = now - timedelta(days=7), now + timedelta(days=90)
    items, page = [], None
    while True:
        args = {
            "calendarId": token.calendar_id,
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": True,
            "maxResults": 2500,
            "showDeleted": False,
        }
        if page:
            args["pageToken"] = page
        result = events_api.list(**args).execute()
        items.extend(result.get("items", []))
        page = result.get("nextPageToken")
        if not page:
            break
    zone = user_zone(user)
    seen = _import_events(user, items, start, end, zone)
    conflicts = _notify_google_conflicts(user, now, zone)
    # Remove only app-owned exports whose local block was deleted.
    for mapping in list(
        CalendarExport.objects.filter(user=user, block__isnull=True)
    ):
        try:
            remote = events_api.get(
                calendarId=token.calendar_id, eventId=mapping.google_id
            ).execute()
            if remote.get("extendedProperties", {}).get("private", {}).get(
                "studyflow_owner"
            ) == str(user.pk):
                events_api.delete(
                    calendarId=token.calendar_id, eventId=mapping.google_id
                ).execute()
        except HttpError as exc:
            if exc.resp.status not in (404, 410):
                logger.warning(
                    "Không thể xóa sự kiện Google mồ côi %s", mapping.google_id,
                    exc_info=True,
                )
                continue
        except Exception:
            logger.warning(
                "Không thể xóa sự kiện Google mồ côi %s", mapping.google_id,
                exc_info=True,
            )
            continue
        mapping.delete()
    exported = 0
    errors = 0
    for block in ScheduleBlock.objects.filter(
        user=user, start_time__lt=end, end_time__gt=now
    ):
        try:
            _export_block(user, token, events_api, block, zone)
            exported += 1
        except Exception:
            errors += 1
            logger.warning(
                "Không thể xuất khung học %s lên Google Calendar", block.pk,
                exc_info=True,
            )
    token.last_synced_at = now
    token.save(update_fields=["last_synced_at"])
    return {
        "imported": len(seen),
        "exported": exported,
        "conflicts": conflicts,
        "errors": errors,
    }
