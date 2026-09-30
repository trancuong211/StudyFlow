from datetime import datetime, timedelta, time
from django.utils import timezone
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock

class ScheduleOptimizer:
    """
    Thuật toán lập lịch thông minh (Constraint & Greedy Scheduling Engine).
    Sắp xếp các task cần làm vào các khoảng thời gian trống (free slots) phù hợp:
    1. Lấy tất cả task chưa hoàn thành và chưa được xếp lịch (hoặc xếp lại các block chưa lock).
    2. Bảo toàn tuyệt đối các block đã bị KHÓA (is_locked=True).
    3. Ưu tiên task: Earliest Deadline First (EDF) kết hợp Trọng số Priority (Khẩn cấp -> Cao -> Trung bình -> Thấp).
    4. Tìm kiếm khung giờ học khả thi (mặc định 08:00 - 22:00, ngắt quãng nghỉ).
    """

    def __init__(self, user, start_date=None, days_ahead=7, study_hours=(8, 22)):
        self.user = user
        self.start_date = start_date or timezone.localdate()
        self.days_ahead = days_ahead
        self.study_start_hour, self.study_end_hour = study_hours

    def get_existing_busy_intervals(self):
        """Lấy tất cả các khoảng thời gian bận (đã có block locked) trong khoảng xem xét."""
        start_dt = timezone.make_aware(datetime.combine(self.start_date, time(0, 0)))
        end_dt = start_dt + timedelta(days=self.days_ahead)

        locked_blocks = ScheduleBlock.objects.filter(
            user=self.user,
            is_locked=True,
            start_time__gte=start_dt,
            end_time__lte=end_dt
        ).order_by('start_time')

        busy_intervals = []
        for b in locked_blocks:
            busy_intervals.append((b.start_time, b.end_time))
        return busy_intervals

    def find_free_slots(self, busy_intervals):
        """Tìm các khoảng thời gian trống theo từng ngày trong khung giờ học."""
        free_slots = []
        current_time = timezone.now()

        for day_offset in range(self.days_ahead):
            current_day = self.start_date + timedelta(days=day_offset)
            day_start = timezone.make_aware(datetime.combine(current_day, time(self.study_start_hour, 0)))
            day_end = timezone.make_aware(datetime.combine(current_day, time(self.study_end_hour, 0)))

            # Nếu là ngày hôm nay, chỉ xếp từ thời điểm hiện tại + 15 phút
            if current_day == timezone.localdate():
                earliest_start = current_time + timedelta(minutes=15)
                if earliest_start > day_start:
                    day_start = earliest_start

            if day_start >= day_end:
                continue

            # Lọc các block bận trùng với ngày này
            day_busy = [
                (max(day_start, b_start), min(day_end, b_end))
                for b_start, b_end in busy_intervals
                if b_start < day_end and b_end > day_start
            ]
            day_busy.sort(key=lambda x: x[0])

            # Tính các khe trống (free slots)
            slot_cursor = day_start
            for b_start, b_end in day_busy:
                if b_start > slot_cursor:
                    free_slots.append((slot_cursor, b_start))
                slot_cursor = max(slot_cursor, b_end)

            if slot_cursor < day_end:
                free_slots.append((slot_cursor, day_end))

        return free_slots

    def run(self):
        """
        Thực thi thuật toán lập lịch.
        Xóa các block tự động cũ chưa lock, sau đó phân bổ các task vào khe trống.
        """
        # 1. Xóa các block tự động cũ chưa bị khóa
        ScheduleBlock.objects.filter(
            user=self.user,
            is_auto_generated=True,
            is_locked=False,
            start_time__gte=timezone.now()
        ).delete()

        # 2. Lấy các task cần lập lịch
        tasks = Task.objects.filter(
            user=self.user,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
        ).order_by('deadline', '-priority')

        busy_intervals = self.get_existing_busy_intervals()
        free_slots = self.find_free_slots(busy_intervals)

        created_blocks = []
        slot_index = 0

        for task in tasks:
            needed_minutes = task.estimated_duration or 60
            while needed_minutes > 0 and slot_index < len(free_slots):
                slot_start, slot_end = free_slots[slot_index]
                slot_duration = int((slot_end - slot_start).total_seconds() / 60)

                if slot_duration < 30:  # Khe quá nhỏ (< 30 phút), bỏ qua
                    slot_index += 1
                    continue

                # Phân bổ tối đa 120 phút mỗi session để tránh kiệt sức
                allocated_minutes = min(needed_minutes, slot_duration, 120)
                block_end = slot_start + timedelta(minutes=allocated_minutes)

                # Không xếp lịch vượt quá deadline của task
                if block_end > task.deadline:
                    # Task không kịp hoàn thành trước deadline trong slot này
                    break

                block = ScheduleBlock.objects.create(
                    user=self.user,
                    task=task,
                    title=f"[Học] {task.title}",
                    start_time=slot_start,
                    end_time=block_end,
                    is_auto_generated=True,
                    is_locked=False,
                )
                created_blocks.append(block)
                needed_minutes -= allocated_minutes

                # Cập nhật lại slot hiện tại hoặc chuyển slot kế tiếp
                if block_end + timedelta(minutes=15) < slot_end:
                    # Nghỉ 15 phút trước block tiếp theo
                    free_slots[slot_index] = (block_end + timedelta(minutes=15), slot_end)
                else:
                    slot_index += 1

            if needed_minutes <= 0:
                task.is_scheduled = True
                task.save(update_fields=['is_scheduled'])

        return created_blocks
