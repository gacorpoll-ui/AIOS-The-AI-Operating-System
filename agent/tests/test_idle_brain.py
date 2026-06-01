"""Tests for Idle Intelligence (Background Brain)."""

import pytest
import time
import json
from unittest.mock import MagicMock, patch
from agent.core.idle_brain import IdleBrain
from agent.core.blackbox import TamperProofBlackBox


class TestIdleBrain:

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    @pytest.fixture
    def idle(self, bb):
        idle = IdleBrain(
            config={"enabled": True, "idle_timeout": 0.1, "cycle_interval": 0.1, "max_tasks_per_cycle": 3},
            black_box=bb,
        )
        idle.start()
        yield idle
        idle.stop()

    def test_record_activity_resets_idle(self, idle):
        idle.record_activity()
        assert idle.is_currently_idle() is False
        assert idle.time_since_activity() < 1

    def test_enters_idle_after_timeout(self, idle):
        idle.record_activity()
        time.sleep(0.5)  # Wait for idle_timeout (0.1s)
        assert idle.is_currently_idle() is True

    def test_get_status_returns_dict(self, idle):
        status = idle.get_status()
        assert "enabled" in status
        assert "is_idle" in status
        assert "wakeup_report" in status
        assert "seconds_since_activity" in status

    def test_can_disable(self, idle):
        idle.disable()
        assert idle.enabled is False

    def test_can_re_enable(self, idle):
        idle.disable()
        idle.enable()
        assert idle.enabled is True

    def test_disable_logged_to_black_box(self, bb):
        idle = IdleBrain(config={"enabled": True}, black_box=bb)
        idle.disable()
        chain = bb.get_chain(10)
        disable_events = [e for e in chain if "idle_disabled" in str(e.get("data", {}).get("type", ""))]
        assert len(disable_events) >= 1

    def test_wakeup_report_max_5_bullets(self, idle):
        # Simulate wakeup
        idle._idle_tasks_done = ["task1", "task2", "task3", "task4", "task5", "task6"]
        idle._generate_wakeup_report()
        assert len(idle._wakeup_report) <= 5

    def test_wakeup_report_logged_to_black_box(self, idle, bb):
        idle.record_activity()
        time.sleep(0.5)
        # Trigger wakeup
        idle.record_activity()
        chain = bb.get_chain(20)
        wakeup_events = [e for e in chain if e.get("event_type") == "idle_activity"]
        assert len(wakeup_events) >= 1

    def test_idle_event_entered_logged(self, idle, bb):
        idle.record_activity()
        time.sleep(0.5)
        chain = bb.get_chain(20)
        enter_events = [e for e in chain if "entered_idle" in str(e.get("data", {}).get("type", ""))]
        assert len(enter_events) >= 1

    def test_task_queue_processed_during_idle(self, bb):
        mock_tq = MagicMock()
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.status = "pending"
        mock_task.goal = "Test task"
        mock_tq.get_next.return_value = mock_task

        idle = IdleBrain(
            config={"enabled": True, "idle_timeout": 0.1, "cycle_interval": 0.1},
            black_box=bb,
            task_queue=mock_tq,
        )
        idle.start()
        time.sleep(0.5)
        idle.stop()

        # Verify task queue was accessed
        assert mock_tq.get_next.called

    def test_prediction_prewarm_during_idle(self, bb):
        mock_pred = MagicMock()
        mock_pred.predict.return_value = []

        idle = IdleBrain(
            config={"enabled": True, "idle_timeout": 0.1, "cycle_interval": 0.1},
            black_box=bb,
            prediction=mock_pred,
        )
        idle.start()
        time.sleep(0.5)
        idle.stop()

        # Verify prediction was called
        assert mock_pred.predict.called
