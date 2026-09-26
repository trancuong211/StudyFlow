import os
from typing import List
from ..api.schemas import TaskInputSchema, RiskAnalysisResponse, DailySummaryResponse

class AIAnalyzer:
    """
    Phân tích mật độ lịch bận và rủi ro deadline bằng OpenAI / Claude API hoặc Rule-based engine.
    """

    @classmethod
    def analyze_risks(cls, tasks: List[TaskInputSchema]) -> RiskAnalysisResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Nếu có OpenAI API Key, có thể gọi trực tiếp SDK
        if api_key and not api_key.startswith("your-"):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                
                tasks_text = "\n".join([
                    f"- {t.title} (Hạn: {t.deadline}, Ưu tiên: {t.priority}, Thời lượng: {t.estimated_duration}m, Đã xếp lịch: {t.is_scheduled})"
                    for t in tasks
                ])
                prompt = (
                    "Bạn là trợ lý AI chuyên về năng suất học tập và quản lý thời gian. "
                    "Hãy phân tích danh sách các deadline sau và đưa ra cảnh báo rủi ro súc tích:\n"
                    f"{tasks_text}\n\n"
                    "Trả về kết quả gồm: mức độ rủi ro (LOW, MEDIUM, HIGH, CRITICAL), tóm tắt và lời khuyên hành động."
                )
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.3
                )
                ai_content = response.choices[0].message.content
                return RiskAnalysisResponse(
                    title="Phân tích rủi ro deadline từ AI",
                    summary=ai_content,
                    risk_level="HIGH" if len(tasks) > 5 else "MEDIUM",
                    advice="Hãy tập trung giải quyết các bài tập có độ ưu tiên cao trước và bật Pomodoro để không xao nhãng."
                )
            except Exception as e:
                # Nếu lỗi gọi OpenAI, tiếp tục với fallback
                pass

        # Rule-based Engine fallback
        unscheduled_count = sum(1 for t in tasks if not t.is_scheduled)
        total_duration = sum(t.estimated_duration for t in tasks)

        if unscheduled_count > 3:
            return RiskAnalysisResponse(
                title=f"Cảnh báo: Có {unscheduled_count} công việc chưa được xếp vào lịch!",
                summary=f"Bạn còn {len(tasks)} deadline sắp tới với tổng thời lượng ước tính {total_duration} phút, trong đó {unscheduled_count} việc chưa có khung giờ học.",
                risk_level="HIGH",
                advice="Hãy bấm nút 'Tự Động Sắp Lịch' trên trang Lịch để hệ thống phân bổ các khung giờ ôn tập tối ưu."
            )
        else:
            return RiskAnalysisResponse(
                title="Lịch trình học tập đang ổn định",
                summary=f"Bạn có {len(tasks)} công việc đang trong tiến độ. Hầu hết đã được phân bổ vào các block thời gian hợp lý.",
                risk_level="LOW",
                advice="Duy trì nhịp độ làm việc hiện tại và nghỉ ngơi hợp lý."
            )

    @classmethod
    def daily_summary(cls, tasks: List[TaskInputSchema], blocks_count: int) -> DailySummaryResponse:
        priorities = [t.title for t in tasks if t.priority in ['Cao', 'Khẩn cấp', 'HIGH', 'URGENT']][:3]
        if not priorities and tasks:
            priorities = [tasks[0].title]

        return DailySummaryResponse(
            headline="Tóm tắt kế hoạch học tập hôm nay",
            summary_text=f"Hôm nay bạn có {len(tasks)} công việc cần hoàn thành và {blocks_count} khung giờ học tập đã lên lịch sẵn.",
            key_priorities=priorities or ["Không có task khẩn cấp hôm nay."],
            encouragement="Hãy bắt đầu với phiên Pomodoro đầu tiên để tạo đà học tập hiệu quả!"
        )
