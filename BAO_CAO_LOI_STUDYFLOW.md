# Báo cáo debug hệ thống StudyFlow (WEBLTPY)

- **Ngày chạy:** 21/11/2026
- **Môi trường:** Python 3.12.3, Django 5.2.17, SQLite (`USE_SQLITE=True`), `DEBUG=True`
- **Phạm vi:** `apps/*`, `studyflow/*`, `ai_service/*` (đọc code + chạy test + chạy thử nghiệm ngẫu nhiên)
- **Ghi chú:** chưa sửa gì trong mã nguồn. Các file test tạm dùng để dò lỗi đã được xóa.

---

## 1. Tóm tắt

| Nhóm | Số lượng |
|---|---|
| Lỗi đã tái hiện bằng cách chạy | 3 |
| Điểm yếu phát hiện khi đọc code (chưa tái hiện riêng) | 5 |
| Lỗi vặt từ ruff | 2 loại (import thừa, thiếu `raise ... from`) |
| Phần chưa kiểm tra được | 4 nhóm (mục 5) |

Không có lỗi làm sai dữ liệu nghiêm trọng hay lỗi 500 ở các ca biên đã thử.

---

## 2. Lỗi đã tái hiện (xác nhận bằng cách chạy)

### Lỗi 1. Không sửa được khung học cũ của công việc đã hoàn thành

- **Mức độ:** Trung bình (ảnh hưởng người dùng)
- **Vị trí:** `apps/scheduler/forms.py` (`BlockForm.__init__`), `apps/scheduler/models.py` (`ScheduleBlock.clean`)
- **Triệu chứng:** mở form sửa khung học của việc đã hoàn thành, đổi tiêu đề rồi lưu thì form trả về HTTP 200 kèm lỗi, không lưu được:
  - `task`: *"Hãy chọn một lựa chọn hợp lệ. Lựa chọn đó không phải là một trong các lựa chọn khả thi."*
  - `__all__`: *"Công việc này đã hoàn thành."*
- **Nguyên nhân:**
  1. `BlockForm` lọc `Task.objects.filter(user=user).exclude(status="COMPLETED")`, nên việc hiện tại của khung không nằm trong danh sách chọn.
  2. `ScheduleBlock.clean()` luôn báo lỗi khi `task.status == COMPLETED`, kể cả khi người dùng chỉ đổi tiêu đề hoặc ghi chú.
  3. Việc kéo thả khung cũ trên calendar cũng bị chặn cùng lý do, vì `api_update_block` gọi `full_clean()`.
- **Cách sửa gợi ý:**
  - Thêm việc hiện tại của khung vào queryset khi đang sửa (`| Q(pk=self.instance.task_id)`).
  - Trong `clean()`, chỉ báo lỗi "đã hoàn thành" khi người dùng đổi sang việc khác hoặc dời khung vào tương lai.

### Lỗi 2. Quá nhiều truy vấn database (N+1)

- **Mức độ:** Trung bình (hiệu năng, tăng theo dữ liệu)
- **Vị trí:** `apps/scheduler/progress.py` (`planned_minutes`), gọi `apps/scheduler/availability.py` (`busy_intervals`) cho từng khung
- **Số liệu đo** (1 người dùng, 30 việc, 90 khung, 10 lịch bận lặp hằng tuần):

| Thao tác | Số truy vấn |
|---|---|
| `GET /tasks/` | 274 |
| `GET /scheduler/` | 287 |
| `ScheduleOptimizer.run()` | 595 |
| `planning_context()` | 359 |
| `GET /scheduler/api/events/` | 7 |
| `GET /` (dashboard) | 11 |

- **Nguyên nhân:** mỗi khung trong `planned_minutes()` gọi `busy_intervals()`, mỗi lần gồm 2 truy vấn (BusyPeriod và GoogleCalendarEvent). Hàm này lại được gọi lặp cho từng việc ở `task_list`, `calendar_view`, `optimizer.run`, `planning_context`.
- **Tác động:** trên SQLite local vẫn dưới 0,5 giây, nhưng trên Postgres ở xa (Render) mỗi truy vấn tốn vài ms, nên các trang này có thể chậm vài giây khi dữ liệu tăng.
- **Cách sửa gợi ý:** tải danh sách bận một lần cho cả khoảng thời gian cần xét, rồi truyền vào `planned_minutes(task, now, busy=...)`.

### Lỗi 3. Khung đầu tiên bắt đầu ở giờ lẻ và dịch mỗi lần chạy lại

- **Mức độ:** Thấp (thẩm mỹ, gây khó hiểu)
- **Vị trí:** `apps/scheduler/engine/optimizer.py` (`find_free_slots`, biến `earliest = now + 15 phút`)
- **Triệu chứng:** khung xếp cho hôm nay bắt đầu đúng thời điểm `now + 15 phút`, ví dụ `18:20:56.289935`. Chạy lại lần nữa thì khung dịch thêm vài mili-giây, nên 17/60 người dùng thử nghiệm bị báo "không idempotent" (chỉ lệch sub-giây, số khung không đổi).
- **Cách sửa gợi ý:** làm tròn `earliest` lên bội số 5 hoặc 15 phút (và bỏ giây, micro-giây).

---

## 3. Điểm yếu phát hiện khi đọc code (chưa tái hiện riêng)

### Điểm 4. Lý do "thiếu thời gian" gây hiểu nhầm với việc có deadline xa

- **Vị trí:** `optimizer.py` (`self.report`), `scheduler/views.py` (`calendar_view`)
- **Mô tả:** thuật toán chỉ xếp trong 7 ngày tới (`days_ahead=7`). Việc có deadline sau hơn 7 ngày mà chưa xếp đủ vẫn bị ghi là *"Không đủ thời gian trước deadline trong khung giờ học và giới hạn mỗi ngày"*, dù có thể chỉ là chưa tới lượt. Cờ `is_scheduled` cũng chỉ thành True khi đã xếp đủ toàn bộ.
- **Gợi ý:** phân biệt "ngoài cửa sổ 7 ngày" với "thật sự không đủ chỗ", hoặc xếp theo cửa sổ dài hơn cho việc có deadline xa.

### Điểm 5. Xếp lịch lỗi nhưng người dùng vẫn thấy thành công

- **Vị trí:** `apps/tasks/views.py` (`_auto_schedule`)
- **Mô tả:** hàm bọc `ScheduleOptimizer.run()` trong `try/except Exception` chỉ ghi log. Khi xếp lịch lỗi, `task_create` và `task_update` vẫn hiện "Đã thêm/Cập nhật thành công".
- **Gợi ý:** trả về trạng thái thành công hoặc thất bại và hiện cảnh báo cho người dùng.

### Điểm 6. Đồng bộ Google định kỳ không xử lý xung đột mới

- **Vị trí:** `studyflow/settings.py` (`CELERY_BEAT_SCHEDULE`, tác vụ `sync_connected_calendars` chạy mỗi 900 giây), `apps/calendar_sync/services.py`
- **Mô tả:** sau mỗi lần đồng bộ, sự kiện Google mới có thể đè lên khung học đã xếp. Hệ thống chỉ tô đỏ khung đó trên calendar. Không tự xếp lại, không tạo thông báo.
- **Gợi ý:** sau khi đồng bộ, nếu phát hiện khung bị trùng thì tạo `Notification` hoặc tự chạy lại lập lịch cho các khung tự tạo chưa khóa.

### Điểm 7. `sync_calendar` giữ khóa lâu và dễ hỏng cả đợt

- **Vị trí:** `apps/calendar_sync/services.py` (`sync_calendar`)
- **Mô tả:**
  - Hàm có `@transaction.atomic` và `select_for_update()` trên dòng user, nhưng gọi API Google (mạng) bên trong transaction, nên khóa bị giữ lâu.
  - Một khung xuất lỗi (ví dụ ném `ValueError("...ID trùng.")`) làm rollback cả đợt, kể cả phần nhập sự kiện đã xong.
- **Gợi ý:** tách phần gọi mạng ra ngoài transaction, và xử lý lỗi từng khung riêng (ghi nhận lỗi rồi đi tiếp).

### Điểm 8. File `.env` nằm trong file zip

- **Mô tả:** zip chứa `.env` với `DB_PASSWORD` thật (đã kiểm tra: `.env` **không** bị commit vào git, chỉ `.env.example` được theo dõi).
- **Rủi ro:** lộ mật khẩu nếu chia sẻ zip nguyên trạng.
- **Gợi ý:** loại `.env` khỏi file nén khi chia sẻ; nếu đã chia sẻ ở nơi khác thì đổi mật khẩu.

---

## 4. Lỗi vặt từ phân tích tĩnh (ruff)

**Import thừa (F401):**
- `ai_service/main.py:2` (`CORSMiddleware`)
- `apps/browser_checks.py:23` (`BusyPeriod`)
- `apps/calendar_sync/views.py:10` (`timezone`)
- `studyflow/urls.py:3-4` (`settings`, `static`)

**Thiếu `raise ... from err` (B904):**
- `apps/accounts/forms.py:19`
- `apps/accounts/models.py:33`
- `apps/calendar_sync/fields.py:29`
- `apps/calendar_sync/services.py:218`
- `apps/resources/views.py:66`

**Biến gán nhưng không dùng (F841):** `apps/test_completion.py:128, 209` (trong test).

Các cảnh báo "hardcoded password" (S105, S106) chủ yếu nằm trong test và hằng số URL token của Google, không phải mật khẩu thật. `bandit` (mức trung bình trở lên) không có phát hiện.

---

## 5. Phần chưa kiểm tra được

| Hạng mục | Lý do chưa kiểm tra |
|---|---|
| Google Calendar thật (OAuth, đồng bộ 2 chiều) | Không có tài khoản/thông tin OAuth; chỉ có test mock trong dự án |
| Tranh chấp đồng thời (hai request cùng lúc) | SQLite không khóa dòng thật; `select_for_update` chỉ có tác dụng trên Postgres |
| Giao diện và JavaScript (FullCalendar kéo thả, timer Pomodoro, Tailwind) | Chỉ chạy được phía server, không có trình duyệt |
| FastAPI AI service (`ai_service/`) và Celery/Redis khi chạy thật | Chỉ kiểm tra phần Django gọi sang service và nhánh dự phòng "AI service unavailable"; chưa chạy service riêng, worker, beat |
| Gửi email thật (SMTP), reset mật khẩu qua email | Chỉ có test dùng mock |
| Triển khai trên Render/Docker (`render.yaml`, `docker/*`, `scripts/start-web.sh`) | Chỉ đọc cấu hình, chưa build hay deploy |
| Tải thật với nhiều người dùng, dữ liệu lớn | Chỉ đo 1 người dùng với 30 việc, 90 khung |
| Upload tệp lớn/độc hại ở mức hệ thống | Chỉ đọc code kiểm tra đuôi tệp (≤ 10 MB, danh sách đuôi cho phép) |

---

## 6. Những gì đã kiểm tra và ổn

- `manage.py check`, `makemigrations --check`: không có vấn đề.
- 96 test có sẵn: tất cả pass (khoảng 49 giây).
- Lịch lặp hằng tuần so với cách tính thủ công: 1.500 ca (múi giờ Việt Nam, New York, London, Auckland, Ấn Độ; lịch qua đêm; `repeat_until`) → 0 sai lệch.
- Thuật toán xếp lịch với 60 người dùng ngẫu nhiên (lịch bận, Google, sự kiện cả ngày, khung khóa, việc quá hạn): không đè lịch bận/Google/khung khác, không vượt deadline, không ngoài giờ học, không quá 120 phút/khối, không vượt giới hạn giờ mỗi ngày, không xếp dư thời lượng.
- API với dữ liệu xấu (ID quá lớn, JSON sai kiểu, ngày năm 9999, thời gian không có múi giờ): trả 400 hoặc 404, không có lỗi 500.
- Cấu hình: có chặn `SECRET_KEY` yếu khi `DEBUG=False`; cookie bảo mật và HSTS bật khi không ở chế độ debug.

---

## 7. Thứ tự ưu tiên sửa đề xuất

1. **Lỗi 1:** sửa form và `clean()` cho khung của việc đã hoàn thành.
2. **Lỗi 2:** gộp truy vấn `busy_intervals` (ảnh hưởng hiệu năng khi lên production).
3. **Điểm 5 và 6:** báo lỗi xếp lịch và thông báo xung đột sau đồng bộ Google.
4. **Điểm 4 và Lỗi 3:** làm rõ lý do thiếu thời gian, làm tròn giờ bắt đầu.
5. **Điểm 7 và 8:** tách mạng khỏi transaction, xử lý `.env` khi chia sẻ.
