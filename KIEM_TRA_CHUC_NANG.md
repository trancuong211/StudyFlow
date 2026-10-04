# StudyFlow — Kiểm tra lại chức năng và các lỗi đã sửa

Ngày: 04/10/2026. Nhánh: `dev`. Thay đổi chưa commit/push.

## Kết luận và phạm vi

Các chức năng chính đã được rà soát qua mã nguồn, kiểm thử HTTP/API và Chromium với dữ liệu giả trên **database kiểm thử riêng**, không reset hoặc xóa database local của người dùng.

Đợt kiểm tra này tìm thấy và sửa thêm lỗi về deadline, cache AI, retry email, tài liệu, bộ lọc, trạng thái công việc và giao diện. Các tính năng tích hợp dịch vụ bên ngoài và triển khai online vẫn cần nghiệm thu bằng cấu hình/tài khoản thật. Kết quả local không được xem là bằng chứng đã deploy hoặc đã đồng bộ với tài khoản Google thật.

## Các vấn đề đã sửa trong đợt này

| Vấn đề | Hành vi sau khi sửa | Tệp chính |
|---|---|---|
| Đổi deadline có thể để khung thủ công chưa khóa nằm sau deadline mới | Từ chối thay đổi khi khung thủ công hoặc đã khóa sẽ vi phạm; khung tự động chưa khóa sau hạn mới vẫn được dọn | `apps/tasks/views.py` |
| AI trả phân tích/tóm tắt cũ trong 20 giây dù vừa thay đổi dữ liệu | Chỉ dùng lại cache khi dấu vân tay dữ liệu khớp; sửa deadline hoặc hoàn thành task làm mới kết quả ngay | `apps/ai_assistant/services.py` |
| Email tóm tắt ngày thất bại bị bỏ qua ở lần chạy kế tiếp | Thử gửi lại thông báo hiện có trong khung chạy 07:00–07:59 theo múi giờ user; không tạo trùng thông báo/insight | `apps/notifications/tasks.py` |
| Link tệp hiện tại trong form chỉnh tài liệu dẫn tới `/media/` trả 404 | Widget dùng route download có kiểm tra đăng nhập và quyền sở hữu | `apps/resources/forms.py`, `apps/resources/templates/resources/widgets/private_file_input.html` |
| Thay/xóa tệp cũ trước khi transaction thành công có thể làm mất tệp khi rollback | Chỉ xóa tệp cũ sau `transaction.on_commit`; rollback giữ tệp cũ | `apps/resources/views.py` |
| Bộ lọc số dạng Unicode hoặc chuỗi quá dài gây lỗi 500 | Chỉ nhận ưu tiên hợp lệ và ID môn học ASCII trong khoảng BigAutoField; bỏ qua bộ lọc sai | `apps/tasks/views.py` |
| Task đã hoàn thành vẫn hiển thị cảnh báo “Chưa xếp lịch” | Hiển thị “Đã hoàn thành”; tên nút đúng với thao tác mở lại công việc | `templates/tasks/task_list.html` |
| Tên user, task và ghi chú dài làm tràn giao diện full-width | Nội dung dài xuống dòng; tên trên navbar được rút gọn; lịch sử Pomodoro cho phép xuống hàng | `static/css/styles.css`, `templates/components/navbar.html`, `templates/pomodoro/timer.html` |
| Menu sidebar xuất hiện ở trang chưa đăng nhập dù không có sidebar; navbar tràn ở 320px | Chỉ render nút sidebar khi đã đăng nhập; giảm padding nút auth trên mobile | `templates/components/navbar.html` |
| Calendar che sự kiện trước 06:00 và sau 23:00 | Hiển thị đủ 00:00–24:00; vùng lịch cuộn theo chiều cao màn hình và mở gần giờ bắt đầu học; kiểm tra sự kiện lúc 01:00 và nút chỉ đọc của Google event | `templates/scheduler/calendar.html` |
| CSS build chưa quét template widget trong app | Bổ sung nguồn `apps/**/templates` và build lại asset | `static/css/tailwind-input.css`, `tailwind.config.js` |

Giữ bố cục full-width theo yêu cầu trước đó, không thêm lại giới hạn chiều rộng cho trang.

## Phạm vi đã kiểm tra

| Nhóm chức năng | Bằng chứng |
|---|---|
| Tài khoản | Đăng ký, email trùng không phân biệt hoa/thường, đăng nhập username/email, logout, cập nhật múi giờ/giờ học, đổi/reset mật khẩu, token reset không dùng lại |
| Quản lý user/phân quyền | User thường không vào admin; superuser xem được danh sách và form quản lý user; kiểm tra quyền sở hữu các thao tác sửa/xóa |
| Môn học và công việc | CRUD, tìm kiếm/lọc, trường bắt buộc, deadline, hoàn thành/mở lại, dọn lịch tương lai, xóa môn giữ task/tài liệu |
| Thuật toán lập lịch | Mục tiêu ngày, deadline, ưu tiên, thời lượng còn thiếu, lịch bận/lịch Google, lịch lặp, khung thủ công/đã khóa, chạy lại không nhân đôi |
| Calendar | Trang ngày/tuần/tháng và API sự kiện; chỉnh khung, khóa, validation kéo–thả API, lịch bận CRUD, range không hợp lệ, hiển thị sự kiện lúc 01:00 |
| Pomodoro | Bắt đầu, pause/resume, reload giữ trạng thái, hủy có xác nhận, chống kết thúc sớm/trùng, chỉ WORK hoàn thành được cộng |
| Tài liệu | CRUD link/file, upload/download, thay tệp, giới hạn kích thước/loại tệp, tải riêng tư, rollback và dọn file sau commit |
| Nhắc việc | Danh sách và đánh dấu đọc riêng từng user, chống trùng, retry SMTP và tóm tắt ngày bằng mock |
| AI/FastAPI | Risk/tóm tắt/thói quen, cache theo dữ liệu, rules fallback, xác thực API nội bộ, validation payload, OpenAI narrative bằng mock |
| Google Calendar | OAuth lỗi/state, token mã hóa, import/export/mapping bằng mock, timezone của sự kiện cả ngày; giao diện chỉ đọc dùng sự kiện giả |
| Giao diện | 24 trang sau đăng nhập ở 375/800/1920px; 3 trang auth ở 320/375/800/1920px; thử chuỗi dài, không tràn ngang, không pageerror JavaScript; sidebar mở/đóng bằng Escape |

## Kiểm thử và cách chạy lại

```sh
source .venv/bin/activate
python manage.py test --verbosity 1
python manage.py check
python manage.py makemigrations --check --dry-run
npm run build
python manage.py collectstatic --noinput
git diff --check
```

Kiểm tra trình duyệt được tách riêng để bộ test thông thường không phụ thuộc Chromium:

```sh
pip install -r requirements-dev.txt
python -m playwright install chromium
python manage.py test apps.browser_checks --verbosity 1
```

- Bộ kiểm thử Django/FastAPI: **98/98 đạt**.
- Kiểm thử Chromium: **4/4 đạt**, gồm 84 lượt kiểm tra trang/kích thước và luồng thao tác thực.
- Regression mới: `apps/test_review.py`; workflow HTTP mới: `apps/test_workflows.py`.
- Test browser: `apps/browser_checks.py`; ảnh nằm trong `test-results/ui-review/` (được gitignore).
- Django check: không lỗi. Migration check: không thiếu migration. Build/collectstatic và diff check: đạt.
- `npm audit`: không báo lỗ hổng tại thời điểm chạy.
- `pip-audit --disable-pip --no-deps -r requirements-lock.txt`: không báo lỗ hổng đã biết trong dependency runtime đã khóa.
- `docker compose config --quiet`: cấu hình hợp lệ; Docker daemon chưa chạy nên chưa chạy container.

## Các phần chưa được nghiệm thu thực tế

1. **Deploy online và URL public:** vẫn chưa có URL production được kiểm chứng trong phiên này; đây là yêu cầu tối thiểu của đề môn học.
2. **PostgreSQL + Redis/Celery:** chưa chạy end-to-end trên máy vì Docker daemon không hoạt động. Test local dùng SQLite; khóa/concurrency PostgreSQL và worker/beat cần kiểm chứng khi chạy môi trường đầy đủ.
3. **Google OAuth thật:** cần client ID/secret, consent/test user và redirect URI hợp lệ. Mock không chứng minh đăng nhập/import/export bằng tài khoản Google thật.
4. **SMTP thật:** cần cấu hình gửi email cho web/worker; local đang dùng console/locmem. Retry email không bảo đảm exactly-once nếu tiến trình dừng ngay sau SMTP gửi.
5. **OpenAI thật:** cần API key/model hỗ trợ structured output. Rules fallback đã hoạt động; chưa thực hiện gọi provider thật trong đợt kiểm tra này.

Ứng dụng có các luồng chính để demo local. Để kết luận đáp ứng đầy đủ đề và hoạt động production, cần hoàn thành các bước nghiệm thu trên; không thể khẳng định toàn hệ thống không còn lỗi chỉ từ test local.
