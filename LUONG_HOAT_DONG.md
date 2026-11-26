# Luồng hoạt động của hệ thống StudyFlow

Tài liệu mô tả cách hệ thống StudyFlow vận hành từ lúc người dùng gửi request đến khi dữ liệu được xử lý, lưu trữ và các tác vụ nền được thực thi. Nội dung bám theo mã nguồn hiện tại trong repository.

## 1. Tổng quan

StudyFlow là ứng dụng Django lập kế hoạch học tập cá nhân, gồm các khối chức năng:

- Tài khoản, xác thực, múi giờ và mục tiêu học.
- Môn học, công việc và deadline.
- Lịch bận, khung học và thuật toán tự lập lịch.
- Pomodoro lưu trạng thái trên server.
- Tài liệu học tập riêng tư.
- Nhắc việc trong ứng dụng và qua email.
- Phân tích AI (rủi ro deadline, thói quen, tóm tắt ngày).
- Đồng bộ Google Calendar.

Điểm thiết kế cốt lõi:

1. Thuật toán lập lịch quyết định kế hoạch; AI chỉ diễn giải và đề xuất.
2. Server là nguồn sự thật cho timer Pomodoro và nhắc việc.
3. Mọi truy vấn dữ liệu nghiệp vụ đều giới hạn theo người dùng đang đăng nhập.
4. Các thao tác ghi lịch/timer dùng transaction và khóa row người dùng để tránh tranh chấp.

## 2. Kiến trúc thành phần

```text
Trình duyệt
    |
    | HTTP/HTTPS
    v
Django web (Gunicorn + WhiteNoise)
    |        |                |
    |        |                +--> PostgreSQL (production) / SQLite (local)
    |        +--> Redis ------> Celery worker + Celery Beat
    |                               |
    |                               +--> SMTP (email nhắc việc)
    |                               +--> Google Calendar API
    |
    +--> FastAPI AI service (mạng nội bộ)
             |
             +--> OpenAI API (tùy chọn)
```

Thành phần triển khai trong `docker-compose.yml`:

- `web`: Django, cổng 8000.
- `db`: PostgreSQL.
- `redis`: broker/result backend cho Celery.
- `celery_worker`: chạy tác vụ nền.
- `celery_beat`: lên lịch tác vụ định kỳ.
- `ai_service`: FastAPI nội bộ, không mở cổng ra host.

Luồng URL gốc nằm ở `studyflow/urls.py:7`, mỗi app nghiệp vụ có URL riêng.

## 3. Luồng xử lý một request

```text
Request
  -> SecurityMiddleware
  -> WhiteNoiseMiddleware (static)
  -> SessionMiddleware
  -> CommonMiddleware
  -> CsrfViewMiddleware
  -> AuthenticationMiddleware
  -> AuthenticationRateLimitMiddleware
  -> UserTimezoneMiddleware
  -> View (kiểm tra login, lọc theo user)
  -> Template / JsonResponse
```

Chi tiết:

1. `SecurityMiddleware` và `WhiteNoiseMiddleware` xử lý bảo mật và tài nguyên tĩnh.
2. `AuthenticationRateLimitMiddleware` giới hạn tần suất đăng nhập/đăng ký/reset mật khẩu (`apps/accounts/limits.py:13`). Giới hạn dùng cache dùng chung (Redis ở production), khóa theo IP + username và cửa sổ thời gian.
3. `UserTimezoneMiddleware` đặt timezone theo hồ sơ người dùng trong toàn bộ request (`apps/accounts/timezones.py:13`). Người chưa đăng nhập dùng timezone mặc định.
4. View dùng `@login_required` và luôn lọc `user=request.user` để bảo đảm cô lập dữ liệu.
5. Các view ghi dữ liệu quan trọng bọc trong `transaction.atomic()` và khóa row user bằng `select_for_update()` để tuần tự hóa thao tác lập lịch/timer của cùng một người dùng.

## 4. Luồng tài khoản

### Đăng ký

```text
GET  /accounts/register/  -> hiển thị form
POST /accounts/register/  -> validate
                          -> tạo User
                          -> login ngay
                          -> chuyển về dashboard
```

Mã liên quan: `apps/accounts/views.py:15`.

### Đăng nhập / đăng xuất

- Đăng nhập dùng `LoginView`, chuyển người đã đăng nhập về dashboard (`apps/accounts/views.py:8`).
- Đăng xuất đưa về trang đăng nhập.
- Hồ sơ cho phép cập nhật họ tên, timezone, mục tiêu giờ học/ngày, khung giờ học, tùy chọn nhận email.

### Dữ liệu người dùng

`User` mở rộng `AbstractUser`, có các trường chính (`apps/accounts/models.py`):

- `email` duy nhất.
- `timezone` mặc định `Asia/Ho_Chi_Minh`.
- `daily_study_goal_hours` từ 1 đến 12.
- `study_start_hour`, `study_end_hour`.
- `email_reminders`.
- `is_google_connected`.

`clean()` kiểm tra timezone hợp lệ và giờ kết thúc phải sau giờ bắt đầu.

## 5. Luồng môn học và công việc

### Môn học

CRUD môn học nằm ở `apps/courses/views.py`:

```text
Tạo/Sửa môn -> gán user hiện tại -> lưu
Xóa môn     -> xác nhận -> xóa
```

Môn học có tên, mã, màu hiển thị trên lịch, số tín chỉ, giảng viên, học kỳ, mô tả và trạng thái hoạt động.

### Công việc

CRUD công việc nằm ở `apps/tasks/views.py`:

```text
Tạo task
  -> nhập tiêu đề, deadline, ưu tiên, độ khó, thời lượng
  -> nhập tên môn (tự tạo môn nếu chưa có)
  -> lưu task
  -> chạy lại thuật toán lập lịch cho toàn bộ task
  -> cập nhật trạng thái đã xếp lịch

Sửa task
  -> lưu thay đổi
  -> chạy lại lập lịch
  -> xóa các block auto chưa khóa vượt quá deadline mới
  -> cập nhật trạng thái đã xếp lịch

Hoàn thành task
  -> đặt status = COMPLETED, ghi completed_at
  -> xóa các block tương lai của task
  -> is_scheduled = False
  -> chạy lại lập lịch
```

Chi tiết quan trọng:

- Task có ưu tiên 1-4, độ khó 1-3, trạng thái TODO/IN_PROGRESS/COMPLETED.
- Thời lượng ước tính là số phút cần để hoàn thành.
- `remaining_minutes` = thời lượng ước tính trừ số phút Pomodoro WORK đã hoàn thành.
- Khi đổi deadline, hệ thống chặn nếu còn khung học thủ công hoặc đã khóa nằm sau deadline mới (`apps/tasks/views.py`, `TaskForm.clean`).
- Danh sách task tính lại `is_scheduled` động dựa trên block hợp lệ và thời gian còn lại.

## 6. Luồng lập lịch tự động

Đây là luồng trọng tâm của hệ thống, thực hiện trong `ScheduleOptimizer.run()` (`apps/scheduler/engine/optimizer.py:63`).

### 6.1. Đầu vào

- Người dùng và timezone.
- Cửa sổ lập lịch mặc định 7 ngày (tối đa 31 ngày khi gọi nội bộ).
- Khung giờ học trong ngày của người dùng.
- Mục tiêu số phút học mỗi ngày.
- Danh sách task chưa hoàn thành.
- Lịch bận lặp tuần, block hiện có và sự kiện Google đang chiếm giờ.

### 6.2. Các bước

```text
1. Khóa row user
2. Xóa block auto chưa khóa trong cửa sổ lập lịch
3. Lấy task TODO/IN_PROGRESS
   sắp xếp theo deadline tăng dần, ưu tiên giảm dần, độ khó giảm dần
4. Tính các khoảng bận:
   - block hiện có, mở rộng 15 phút mỗi đầu
   - lịch bận lặp tuần
   - sự kiện Google có is_busy = True
5. Sinh các slot trống trong khung giờ học từng ngày
   - không bắt đầu trước thời điểm hiện tại + 15 phút
6. Tính tải mỗi ngày:
   - số phút block hiện có
   - cộng số phút Pomodoro WORK đã hoàn thành
7. Duyệt từng task theo thứ tự ưu tiên deadline:
   - nhu cầu = remaining_minutes - planned_minutes
   - duyệt các slot còn trống
   - bỏ qua slot bắt đầu sau deadline
   - chia phiên tối đa 120 phút
   - không vượt mục tiêu ngày
   - nghỉ 15 phút giữa hai phiên
   - tạo ScheduleBlock auto
8. Cập nhật is_scheduled cho từng task
9. Ghi báo cáo các task không xếp đủ thời gian
```

### 6.3. Quy tắc quan trọng

- Block `is_locked=True` hoặc không do thuật toán tạo sẽ không bị xóa.
- Block đã chỉnh tay được giữ nguyên khi chạy lại lập lịch.
- Không xếp phiên quá deadline của task.
- Không xếp vượt mục tiêu học mỗi ngày.
- Phiên tối thiểu thực tế là 15 phút; phần nhỏ hơn không được tạo.
- Nếu task quá hạn hoặc không đủ thời gian trước deadline, hệ thống báo lý do thay vì tạo lịch sai.

### 6.4. Kết quả

- Danh sách `ScheduleBlock` mới.
- Báo cáo `report` gồm `task_id`, `title`, `missing_minutes`, `reason`.
- Trạng thái `is_scheduled` được cập nhật qua `refresh_scheduled()` (`apps/scheduler/progress.py:21`).

### 6.5. Các nơi kích hoạt lập lịch

- Người dùng bấm nút lập lịch trên trang calendar (`apps/scheduler/views.py:114`).
- Sau khi tạo task (`apps/tasks/views.py`, `_auto_schedule`).
- Sau khi sửa task hoặc đổi trạng thái hoàn thành.
- Khi cần, AI service cũng mô phỏng slot trống để đánh giá năng lực lập kế hoạch.

## 7. Luồng lịch và tương tác calendar

### 7.1. Hiển thị lịch

`calendar_view` (`apps/scheduler/views.py:27`) chuẩn bị:

- Báo cáo task chưa đủ khung học.
- Danh sách ngày vượt mục tiêu học.

FullCalendar gọi `api_events` (`apps/scheduler/views.py:42`) và nhận về ba loại sự kiện:

| Loại | Màu | Có thể chỉnh |
|------|-----|--------------|
| Khung học | Màu môn học, đỏ nếu trùng lịch | Có |
| Lịch bận | Xám | Không |
| Sự kiện Google | Xanh lá | Không |

Khoảng xem lịch tối đa 95 ngày, có kiểm tra tham số đầu vào.

### 7.2. Kéo thả và khóa khung

```text
Kéo thả block
  -> POST /scheduler/api/blocks/<id>/update/
  -> khóa row user
  -> cập nhật thời gian
  -> mặc định is_locked = True
  -> full_clean() kiểm tra trùng lịch bận/Google/block khác
  -> lưu
  -> cập nhật lại trạng thái task
```

- Toggle khóa: `api_toggle_lock`.
- Sửa/xóa block qua form và view xác nhận.
- Xóa block sẽ tính lại trạng thái đã xếp lịch của task.

### 7.3. Lịch bận

- Lưu ca làm hoặc hoạt động cá nhân.
- Hỗ trợ lặp hàng tuần và ngày kết thúc lặp.
- Khi hiển thị, lịch lặp được mở rộng theo timezone của người dùng (`apps/scheduler/availability.py:6`).
- Thuật toán lập lịch coi các khoảng này là bận.

## 8. Luồng Pomodoro

Timer lưu trạng thái trên server, không tin thời lượng do client gửi.

```text
Bắt đầu
  -> POST /pomodoro/api/start/
  -> khóa row user
  -> nếu đã có phiên active thì trả về phiên đó
  -> tạo phiên với running_since = now
  -> chế độ WORK 25 phút / SHORT_BREAK 5 phút / LONG_BREAK 15 phút

Tạm dừng
  -> cộng dồn elapsed_seconds
  -> running_since = None

Tiếp tục
  -> running_since = now

Kết thúc
  -> chỉ cho phép khi đã đủ thời gian mục tiêu
  -> ghi duration_minutes, end_time, completed = True
  -> is_active = False
  -> cập nhật lại trạng thái task

Hủy
  -> ghi nhận thời gian đã học nhưng completed = False
```

Chi tiết:

- `elapsed()` tính thời gian thực từ `elapsed_seconds` và `running_since`, giới hạn theo mục tiêu phiên (`apps/pomodoro/views.py:16`).
- Chỉ phiên WORK `completed=True` được tính vào thống kê, `remaining_minutes` và tải ngày.
- Endpoint legacy `api_record_session` không còn nhận thời lượng từ client mà chuyển sang luồng finish của server.
- Khi reload trang, client gọi `api_state` để khôi phục trạng thái phiên đang chạy.

## 9. Luồng tài liệu

```text
Thêm tài liệu
  -> nhập tiêu đề, mô tả, link hoặc file
  -> giới hạn file 10 MB
  -> giới hạn định dạng: PDF, Office, văn bản, PNG/JPG
  -> gắn môn học và/hoặc task thuộc chính người dùng
  -> lưu file vào storage

Tải tài liệu
  -> kiểm tra chủ sở hữu
  -> mở file và trả về dạng attachment
  -> không serve công khai qua URL media
```

Mã liên quan: `apps/resources/forms.py`, `apps/resources/views.py:48`. Khi thay file, file cũ được xóa sau khi transaction commit.

## 10. Luồng nhắc việc và email

Celery Beat lên lịch các tác vụ định kỳ (`studyflow/settings.py:215`):

| Tác vụ | Chu kỳ | Chức năng |
|--------|--------|-----------|
| `send_due_reminders` | 5 phút | Nhắc deadline và khung học sắp bắt đầu |
| `daily_briefings` | 15 phút | Tạo briefing lúc 7 giờ sáng theo timezone người dùng |
| `sync_connected_calendars` | 15 phút | Đồng bộ Google Calendar |

### Nhắc deadline

```text
Quét task chưa hoàn thành có deadline trong khoảng
  từ 7 ngày trước đến 24 giờ tới
  -> phân loại: quá hạn / còn <= 1 giờ / còn <= 24 giờ
  -> tạo Notification với dedup_key duy nhất
  -> nếu user bật email và có địa chỉ thì gửi email
  -> ghi emailed_at khi gửi thành công
```

### Nhắc khung học

```text
Quét block bắt đầu trong 30 phút tới
  -> bỏ qua task đã hoàn thành
  -> tạo Notification chống trùng
  -> gửi email nếu được bật
```

### Briefing hằng ngày

```text
Mỗi 15 phút
  -> với từng user đang hoạt động
  -> đổi sang timezone của user
  -> nếu giờ địa phương là 7 giờ
     -> tạo hoặc lấy AI daily summary
     -> tạo Notification chống trùng theo ngày
     -> gửi email nếu được bật
```

Cơ chế chống trùng dùng `dedup_key` duy nhất trên model `Notification` (`apps/notifications/models.py`). Lỗi SMTP không làm mất thông báo trong app; lần chạy sau sẽ thử gửi lại.

## 11. Luồng AI hỗ trợ

### 11.1. Phân tích rủi ro deadline

```text
Người dùng bấm phân tích
  -> AIServiceBridge.analyze_schedule_and_deadlines()
  -> xây planning_context:
       - danh sách task chưa hoàn thành
       - thời gian còn lại, thời gian đã xếp
       - năng lực trống trước deadline
       - thói quen 30 ngày
       - các ngày quá tải
  -> tính fingerprint và kiểm tra cache 5 phút
  -> tính baseline bằng rules
  -> gọi FastAPI /api/v1/analyze-risks
  -> nếu FastAPI/OpenAI lỗi, dùng baseline
  -> lưu AIInsight
```

### 11.2. Tóm tắt ngày

```text
daily_summary()
  -> lấy block và task liên quan trong ngày
  -> tổng phút đã xếp, mục tiêu ngày
  -> gọi FastAPI /api/v1/daily-summary
  -> fallback rules nếu dịch vụ lỗi
  -> lưu AIInsight
```

### 11.3. Phía FastAPI

- Xác thực bằng header `X-Service-Token` (`ai_service/api/endpoints.py:8`).
- Tính rủi ro theo quy tắc trước: quá hạn, thiếu năng lực, khẩn cấp, chưa xếp lịch, ngày quá tải.
- Chỉ khi có `OPENAI_API_KEY` hợp lệ mới gọi LLM để viết lại phần diễn giải.
- Dữ liệu gửi LLM gồm tối đa 50 task và thống kê thói quen; không gửi nội dung file tài liệu.
- Kết quả ghi rõ nguồn `rules` hoặc `openai`.

### 11.4. Thói quen học tập

`habit_analysis()` (`apps/ai_assistant/services.py:22`) tổng hợp 30 ngày Pomodoro WORK:

- Tổng số phiên và tổng phút tập trung.
- Giờ tập trung nhiều nhất (chỉ khi có ít nhất 5 phiên).
- Biểu đồ 7 ngày gần nhất so với mục tiêu ngày.
- Lời khuyên theo dữ liệu.

## 12. Luồng Google Calendar

### 12.1. Kết nối OAuth2

```text
Bấm kết nối
  -> tạo Flow với client_id/client_secret từ môi trường
  -> sinh state, lưu vào session
  -> chuyển sang Google

Google callback
  -> kiểm tra error, code, state
  -> đổi code lấy token
  -> mã hóa và lưu GoogleCalendarToken
  -> đánh dấu user.is_google_connected = True
```

Token được lưu bằng trường mã hóa (`apps/calendar_sync/models.py`, `EncryptedTextField`).

### 12.2. Đồng bộ

`sync_calendar()` (`apps/calendar_sync/services.py:76`):

```text
1. Khóa user và token
2. Refresh access token nếu hết hạn
3. Tải sự kiện Google từ 7 ngày trước đến 90 ngày tới
   - bỏ qua sự kiện do StudyFlow tạo
   - bỏ qua sự kiện đã hủy
   - lưu/cập nhật GoogleCalendarEvent
4. Xóa sự kiện Google cục bộ không còn tồn tại
5. Với block đã bị xóa cục bộ:
   - chỉ xóa event Google nếu có dấu studyflow_owner
6. Với block học tương lai:
   - tạo event mới nếu chưa có mapping
   - cập nhật event nếu nội dung thay đổi
   - chống trùng bằng ID hash
7. Ghi last_synced_at
```

Đặc điểm:

- Đồng bộ một chiều có kiểm soát, không phải hai chiều đầy đủ.
- Sự kiện `transparent` không chiếm giờ.
- Chỉ dọn event do StudyFlow tạo.
- Disconnect chỉ xóa dữ liệu cục bộ, không xóa event đã xuất trên Google.
- Khi đổi `SECRET_KEY`, token cũ không giải mã được và cần kết nối lại.

### 12.3. Ảnh hưởng tới lập lịch

Sự kiện Google có `is_busy=True` được đưa vào `busy_intervals()`. Do đó sau khi đồng bộ, người dùng nên chạy lại lập lịch để tránh lịch bận mới.

## 13. Luồng dashboard

Dashboard (`apps/dashboard/views.py:14`) tổng hợp:

- Số môn học đang hoạt động.
- Số task chưa hoàn thành.
- Deadline trong 3 ngày tới.
- Tổng phút Pomodoro WORK hoàn thành hôm nay.
- Các block học hôm nay.
- AI insight mới nhất và daily summary hôm nay.
- Thói quen 30 ngày.
- Số thông báo chưa đọc.

## 14. Luồng dữ liệu tổng quát của người dùng

```text
Đăng ký
  -> Cấu hình múi giờ, mục tiêu và khung giờ học
  -> Thêm môn học và công việc
  -> Nhập lịch bận lặp tuần
  -> Lập lịch tự động
  -> Xem calendar, kéo thả hoặc khóa khung
  -> Chạy lại lập lịch, giữ nguyên khung đã chỉnh
  -> Học bằng Pomodoro
  -> Tiến độ task cập nhật theo phút WORK hoàn thành
  -> AI phân tích rủi ro và tóm tắt ngày
  -> Nhận thông báo trong app hoặc email
  -> Tùy chọn kết nối Google Calendar để import lịch bận và export khung học
```

## 15. Cô lập dữ liệu và nhất quán

### Cô lập theo người dùng

- Mọi model nghiệp vụ đều có khóa ngoại tới `User`.
- View luôn lọc theo `request.user`.
- Form giới hạn queryset môn học/task theo người dùng hiện tại.
- Tài liệu chỉ tải được qua view kiểm tra chủ sở hữu.

### Nhất quán khi ghi

- `transaction.atomic()` bọc các thao tác tạo/sửa lịch, task, timer.
- `select_for_update()` trên row user tuần tự hóa các thao tác lập lịch đồng thời.
- Ràng buộc database đảm bảo `end_time > start_time`.
- `full_clean()` kiểm tra trùng khung giờ và trùng lịch bận trước khi lưu.

### Chống trùng

- `Notification.dedup_key` duy nhất.
- `GoogleCalendarEvent` duy nhất theo `(user, google_id)`.
- `CalendarExport` duy nhất theo `(user, google_id)`.
- AI insight dùng fingerprint nội dung và thời gian để tái sử dụng kết quả trong 5 phút.

## 16. Tác vụ nền

| Tên | Nơi định nghĩa | Kích hoạt |
|-----|----------------|-----------|
| `send_due_reminders` | `apps/notifications/tasks.py:49` | Beat mỗi 5 phút hoặc lệnh `send_reminders` |
| `daily_briefings` | `apps/notifications/tasks.py:102` | Beat mỗi 15 phút, chỉ chạy lúc 7 giờ địa phương |
| `sync_connected_calendars` | `apps/calendar_sync/tasks.py:10` | Beat mỗi 15 phút |

Celery dùng Redis làm broker và result backend (`studyflow/settings.py:171`). Local có thể chạy job trực tiếp bằng `python manage.py send_reminders` khi không có Redis.

## 17. Môi trường chạy

### Local

- `USE_SQLITE=True`, SQLite mặc định.
- Email in ra console.
- AI service chạy riêng bằng Uvicorn ở cổng 8001.
- Có thể chạy Celery worker/beat nếu có Redis.

### Docker

- Web, worker và beat luôn dùng PostgreSQL dù `.env` local đặt `USE_SQLITE=True`.
- AI service và database/Redis không mở cổng ra host.
- Web chạy migration và collectstatic khi khởi động.
- Worker/beat chờ web healthy.

### Production

- `DEBUG=False`, `SECRET_KEY` mạnh, HTTPS qua reverse proxy.
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` phải đúng.
- Media nằm trên persistent disk; nếu scale nhiều instance cần object storage.
- Chỉ chạy đúng một Celery beat.

## 18. Tóm tắt luồng chính

```text
Người dùng
   |
   v
Django view ---> kiểm tra auth, timezone, rate limit
   |
   +--> CRUD môn học/task ---> tự động lập lịch
   |                              |
   |                              v
   |                        ScheduleOptimizer
   |                        (deadline-first + slot trống
   |                         + giới hạn ngày + giữ khung khóa)
   |                              |
   |                              v
   |                        ScheduleBlock
   |
   +--> Calendar API <--> FullCalendar (kéo thả, khóa, trùng lịch)
   |
   +--> Pomodoro server-side ---> cập nhật tiến độ task
   |
   +--> AI Bridge ---> FastAPI ---> rules/OpenAI ---> AIInsight
   |
   +--> Notification ---> Celery ---> in-app/email
   |
   +--> Google OAuth/sync ---> import lịch bận, export khung học
```

Toàn bộ hệ thống xoay quanh vòng lặp: nhập kế hoạch, tự động xếp lịch, thực thi bằng Pomodoro, đánh giá tiến độ bằng AI và nhắc việc, rồi điều chỉnh lại kế hoạch khi có dữ liệu mới.
