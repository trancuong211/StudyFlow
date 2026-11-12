import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from .main import app
from .services.analyzer import AIAnalyzer, Narrative


class AIAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.payload = {
            "user_id": 1,
            "current_time": "2026-01-02T00:00:00Z",
            "tasks": [
                {
                    "id": 1,
                    "title": "Đồ án",
                    "deadline": "2026-01-03T00:00:00Z",
                    "priority": "Cao",
                    "estimated_duration": 120,
                    "is_scheduled": False,
                    "remaining_minutes": 120,
                    "available_minutes": 10,
                    "cumulative_unscheduled_minutes": 120,
                }
            ],
        }

    def test_internal_auth_required_when_configured(self):
        with patch.dict(os.environ, {"AI_SERVICE_TOKEN": "local-test-token"}):
            self.assertEqual(
                self.client.post(
                    "/api/v1/analyze-risks", json=self.payload
                ).status_code,
                401,
            )
            with patch.object(AIAnalyzer, "_narrative", return_value=None):
                result = self.client.post(
                    "/api/v1/analyze-risks",
                    json=self.payload,
                    headers={"X-Service-Token": "local-test-token"},
                )
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["risk_level"], "HIGH")

    def test_invalid_dates_return_validation_error(self):
        with patch.dict(os.environ, {"AI_SERVICE_TOKEN": ""}):
            self.payload["tasks"][0]["deadline"] = "2026-01-03"
            self.assertEqual(
                self.client.post(
                    "/api/v1/analyze-risks", json=self.payload
                ).status_code,
                422,
            )

    def test_llm_narrative_does_not_override_risk(self):
        with (
            patch.dict(os.environ, {"AI_SERVICE_TOKEN": ""}),
            patch.object(
                AIAnalyzer,
                "_narrative",
                return_value=Narrative(summary="Nhận xét AI", advice="Ưu tiên đồ án"),
            ),
        ):
            result = self.client.post("/api/v1/analyze-risks", json=self.payload).json()
        self.assertEqual(result["risk_level"], "HIGH")
        self.assertEqual(result["source"], "openai")
        self.assertEqual(result["summary"], "Nhận xét AI")

    def test_summary_without_llm(self):
        payload = {
            "user_id": 1,
            "date": "2026-01-02",
            "tasks_due_today": self.payload["tasks"],
            "scheduled_blocks_count": 2,
            "scheduled_minutes": 90,
            "daily_goal_minutes": 240,
        }
        with (
            patch.dict(os.environ, {"AI_SERVICE_TOKEN": ""}),
            patch.object(AIAnalyzer, "_narrative", return_value=None),
        ):
            result = self.client.post("/api/v1/daily-summary", json=payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["key_priorities"], ["Đồ án"])
        self.assertEqual(result.json()["source"], "rules")
