# StudyFlow

Ứng dụng Django lập kế hoạch học tập cá nhân: calendar, deadline, lịch bận, tài liệu, Pomodoro và AI hỗ trợ. Thuật toán lập lịch là trọng tâm; AI chỉ diễn giải dữ liệu và đề xuất.

Bản tổng hợp lỗi đã sửa, bằng chứng kiểm thử và phần cần nghiệm thu: [HOAN_THIEN_DU_AN.md](HOAN_THIEN_DU_AN.md).

Đợt kiểm tra lại ngày 04/10/2026, lỗi sửa thêm và cách chạy test browser: [KIEM_TRA_CHUC_NANG.md](KIEM_TRA_CHUC_NANG.md).

## Tính năng

- Tài khoản: đăng ký, đăng nhập username/email, đổi/reset mật khẩu, múi giờ và mục tiêu học; user/staff/admin.
- Môn học và công việc: CRUD, ưu tiên, độ khó, thời lượng, deadline, tìm kiếm/lọc.
- Calendar: ngày/tuần/tháng, khung học thủ công, kéo–thả, khóa lịch, kiểm tra trùng.
- Lịch bận: ca làm/hoạt động cá nhân, lặp tuần và ngày kết thúc.
- Tự lập lịch tuần: deadline-first, giới hạn giờ/ngày, nghỉ giữa phiên, giữ khung đã chỉnh, báo cáo phần chưa xếp đủ.
- Pomodoro: trạng thái server, pause/resume/reload, chống ghi nhận trùng, thống kê WORK thực.
- Tài liệu: link hoặc file tối đa 10 MB, gắn môn/task, download riêng tư.
- Nhắc việc: trong app và email tùy chọn, Celery/Beat.
- AI: mức rủi ro deadline, thói quen 30 ngày, tóm tắt ngày; OpenAI tùy chọn và fallback theo quy tắc.
- Google Calendar: OAuth, nhập sự kiện bận primary calendar, xuất/cập nhật khung học, refresh token.

## Công nghệ và cấu trúc

Django 5.2 + templates, Tailwind CSS build local, FullCalendar 6 + Luxon; FastAPI; PostgreSQL production/SQLite local; Redis + Celery + django-celery-beat; Gunicorn + WhiteNoise.

```text
studyflow/             Cấu hình Django, Celery, health
apps/accounts/         User, auth, timezone, rate limit
apps/courses/           Môn học
apps/tasks/             Công việc/deadline
apps/scheduler/         Lịch bận, block, optimizer, progress
apps/pomodoro/          Timer persistent
apps/resources/         Tài liệu riêng tư
apps/notifications/     Nhắc việc, email, jobs
apps/calendar_sync/     OAuth, token mã hóa, import/export
apps/ai_assistant/      Bridge AI, insights, thói quen
apps/dashboard/        Dashboard, seed_demo
ai_service/            FastAPI và OpenAI structured output
templates/, static/    Giao diện và tài nguyên
docker/, render.yaml   Triển khai
```

Python 3.11 được dùng khi kiểm thử. Node 22 cần khi sửa/build frontend. Tài nguyên build được lưu trong repo để native Render không cần Node lúc chạy. Python constraints ở requirements-lock.txt; npm dùng package-lock.json.

## Chạy local nhanh

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Windows: kích hoạt bằng `.venv\Scripts\activate`.

Mở http://localhost:8000 và đăng ký tài khoản. .env.example dành cho local: DEBUG=True, USE_SQLITE=True và email console. Không dùng secret mẫu ở production.

Nếu thay template, CSS hoặc JS:

```sh
npm ci
npm run build
python manage.py collectstatic --noinput
```

CSS/calendar chạy local, không cần Tailwind runtime CDN. Google Fonts vẫn là tùy chọn tải font ngoài; khi không có mạng dùng font hệ thống. Giao diện dùng Tailwind 4, cần trình duyệt hiện đại.

### Tạo dữ liệu demo và admin

```sh
python manage.py seed_demo --username studyflow-demo
python manage.py createsuperuser
```

Lệnh demo hỏi mật khẩu, tạo dữ liệu giả riêng và **từ chối ghi đè user đã tồn tại**. Tài khoản demo không có quyền admin. Không tự seed mật khẩu cố định lên production.

### FastAPI local (terminal riêng)

```sh
source .venv/bin/activate
uvicorn ai_service.main:app --host 127.0.0.1 --port 8001 --env-file .env
```

Django dùng AI_SERVICE_URL=http://localhost:8001. Đặt cùng AI_SERVICE_TOKEN ở cả hai tiến trình. OPENAI_API_KEY để trống thì dịch vụ dùng quy tắc; nếu FastAPI tắt, Django cũng fallback. Muốn LLM diễn giải: đặt key hợp lệ và OPENAI_MODEL hỗ trợ structured output trên AI service.

Không đặt key ở JS/template hoặc commit .env. Khi bật LLM, tiêu đề/deadline/thời lượng của tối đa 50 task và thống kê thói quen có thể được gửi tới OpenAI. Tệp tài liệu không được gửi.

### Nhắc việc local

Chạy Redis riêng, rồi mở hai terminal:

```sh
celery -A studyflow worker -l info --concurrency=2
celery -A studyflow beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Cần **đúng một beat**. Không có Redis thì có thể demo job trực tiếp:

```sh
python manage.py send_reminders
```

Email development in ra console. Email thật cần SMTP; worker và web phải cùng EMAIL_* và SITE_URL. Trong hồ sơ có tùy chọn nhận email; thông báo trong app vẫn hoạt động.

## Docker: PostgreSQL + Redis + các dịch vụ

Bật Docker Engine/Desktop trước. Tạo .env, chọn SECRET_KEY và POSTGRES_PASSWORD riêng, rồi:

```sh
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Web ở http://localhost:8000. Compose luôn dùng PostgreSQL cho web/worker/beat, dù .env local có USE_SQLITE=True. Web khởi động bằng Gunicorn, chạy migration và collectstatic. Worker/beat chờ web healthy. AI service và DB/Redis không công khai port host.

Volume giữ PostgreSQL, Redis và tệp tài liệu. Không dùng `docker compose down -v` nếu muốn giữ dữ liệu. Đổi POSTGRES_PASSWORD trong .env không tự đổi mật khẩu của DB đã có volume.

Production cần HTTPS reverse proxy, DEBUG=False, SECRET_KEY mạnh, ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS/SITE_URL đúng. Không chạy public bằng Django runserver.

## Google Calendar

1. Trong Google Cloud, bật Google Calendar API; cấu hình OAuth consent và thêm test user nếu ứng dụng ở chế độ Testing.
2. Tạo OAuth client kiểu Web Application, callback local chính xác: http://localhost:8000/calendar/oauth2callback/.
3. Đặt GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET và GOOGLE_REDIRECT_URI trong .env.
4. Mở “Đồng bộ Google Calendar”, kết nối tài khoản, chọn “Đồng bộ ngay”.
5. Xem sự kiện Google màu xanh lá trên lịch; lập lại kế hoạch để tránh lịch bận mới.

Production dùng callback HTTPS đúng URL thật. Không dùng credential placeholder.

Phạm vi: primary calendar, nhập 7 ngày trước đến 90 ngày tới; xuất các khung học tương lai trong cửa sổ 90 ngày. Sự kiện transparent không chiếm giờ. App chỉ dọn sự kiện có dấu sở hữu StudyFlow khi khung local bị xóa.

Đây không phải đồng bộ mọi chỉnh sửa theo hai chiều: hãy sửa khung học đã xuất tại StudyFlow. Disconnect không xóa sự kiện đã xuất trong Google. Token được mã hóa bằng khóa dẫn xuất từ SECRET_KEY; giữ secret ổn định trên web/worker. Khi đổi secret, phải kết nối lại Google. Backup dữ liệu trước khi nâng cấp/rollback.

## Deploy Render

**Repo có Blueprint, chưa có URL public đã được nghiệm thu trong phiên làm việc này.** Blueprint tạo nhiều tài nguyên trả phí; xem chi phí Render trước khi xác nhận tạo.

1. Đưa phiên bản mã nguồn và asset mới lên repository của bạn.
2. Render → New Blueprint → chọn repo và render.yaml; kiểm tra loại tài nguyên/region/chi phí.
3. Blueprint gồm web, private FastAPI, worker, beat, PostgreSQL, Redis và disk media.
4. Để OPENAI_API_KEY trống nếu chưa dùng LLM. Đặt SITE_URL của worker thành URL HTTPS thật của web.
5. Thêm EMAIL_* / DEFAULT_FROM_EMAIL cho web và worker (có thể dùng nhóm môi trường Django chung).
6. Thêm GOOGLE_* cho web; GOOGLE_REDIRECT_URI phải là URL HTTPS thật + /calendar/oauth2callback/.
7. Chờ web /health/ healthy. Nếu worker/beat lần đầu khởi động trước khi web migrate xong, restart worker/beat sau khi web healthy.
8. Trong shell web chạy `python manage.py createsuperuser`.
9. Nghiệm thu checklist cuối [HOAN_THIEN_DU_AN.md](HOAN_THIEN_DU_AN.md).

Web dùng RENDER_EXTERNAL_HOSTNAME để thêm allowed host/CSRF origin và suy ra SITE_URL. SECRET_KEY/AI_SERVICE_TOKEN được tạo trong env group, dùng chung; giữ nguyên qua các lần deploy. Media nằm ở /var/data/media trên persistent disk. Blueprint giữ web một instance với local disk; nếu scale nhiều instance, cần chuyển sang object storage.

Asset đã build được commit; trước khi sửa giao diện/deploy lại chạy npm ci + npm run build. CI kiểm tra asset chưa cập nhật.

Tham chiếu trường Blueprint và schema: [Render Blueprint reference](https://render.com/docs/blueprint-spec). Script kiểm tra schema chỉ đọc, không deploy:

```sh
pip install -r requirements-dev.txt
python scripts/validate-deployment.py
```

Health kiểm tra DB, không bảo đảm SMTP/Google/OpenAI/Redis đều healthy. Theo dõi log từng dịch vụ.

## Kiểm thử

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 2
npm ci
npm run build
npm audit
python manage.py collectstatic --noinput
git diff --check
```

Đợt kiểm tra mới có 98 test trên SQLite/Python 3.11; gồm API FastAPI, auth, ownership, CRUD, lịch/goal/deadline/busy, timer, tài liệu/rollback, mock Google, email chống trùng/retry và fallback AI/cache. GitHub Actions cấu hình chạy PostgreSQL; chưa coi CI đã đạt nếu chưa có run trên GitHub.

Kiểm tra Chromium riêng (database test tách biệt; không thay dữ liệu local):

```sh
pip install -r requirements-dev.txt
python -m playwright install chromium
python manage.py test apps.browser_checks --verbosity 1
```

Ảnh kiểm tra được lưu ở `test-results/ui-review/` và không đưa vào Git.

Production:

```sh
python manage.py check --deploy
```

Mặc định còn hai cảnh báo HSTS includeSubdomains/preload. Chỉ bật SECURE_HSTS_INCLUDE_SUBDOMAINS và SECURE_HSTS_PRELOAD khi kiểm soát miền và đáp ứng HTTPS trên toàn bộ subdomain; không bật chỉ để làm mất cảnh báo.

Kết quả hai cảnh báo ở trên được kiểm tra với SECRET_KEY dài ít nhất 50 ký tự. Secret 256-bit do Render tự sinh có thể ngắn hơn 50 ký tự và làm Django báo thêm W009 theo kiểm tra độ dài; có thể đặt secret ngẫu nhiên dài hơn trước khi tạo dữ liệu/tokens. Không tự ý đổi secret sau khi đã dùng Google Calendar mà không có kế hoạch kết nối lại.

## Kịch bản demo đồ án

1. Đăng ký hoặc dùng user demo; chỉnh mục tiêu ngày và giờ học.
2. Thêm môn, task có deadline/ưu tiên/thời lượng khác nhau.
3. Nhập ca làm lặp tuần và chạy lập lịch.
4. Chỉ ra ngày không vượt mục tiêu và task thiếu thời gian được báo.
5. Chỉnh/khóa khung, chạy lại: khung đã chỉnh được giữ.
6. Mở timer, pause, reload, resume; cho thấy thống kê chỉ tính WORK hoàn thành.
7. Thêm tài liệu; đăng nhập account khác chứng minh dữ liệu riêng tư.
8. Tạo tóm tắt/rủi ro; giải thích nhãn rules/openai và fallback.
9. Với cấu hình thật: demo thông báo, Google import/export và URL public.

Giới hạn còn lại được công khai trong HOAN_THIEN_DU_AN.md: heuristic không tối ưu toàn cục, chưa có push/SMS, collaboration/SSO, chưa đo hiệu quả học, và chưa nghiệm thu các dịch vụ bên ngoài bằng credential thật.
