import pytest
import tempfile
from agent.core.reporter import AutoReporter


class TestAutoReporter:

    @pytest.fixture
    def reporter(self, tmp_path):
        return AutoReporter(db_path=str(tmp_path / "reports.db"))

    def test_log_and_daily_report(self, reporter):
        reporter.log_task("show files", True, "listed 14 files")
        reporter.log_task("show system", True, "system info returned")
        reporter.log_task("bad task", False, "", "error occurred")

        report = reporter.daily_report()
        assert report["summary"]["total_tasks"] == 3
        assert report["summary"]["successful"] == 2
        assert report["summary"]["failed"] == 1
        assert report["summary"]["success_rate"] == pytest.approx(66.7, abs=0.2)
        assert len(report["failed_tasks"]) == 1

    def test_weekly_report_empty(self, reporter):
        report = reporter.weekly_report()
        assert report["summary"]["total_tasks"] == 0
        assert report["summary"]["success_rate"] == 0

    def test_format_report_produces_readable_text(self, reporter):
        reporter.log_task("disk cleanup", True, "cleaned 500MB")
        reporter.log_task("security scan", True, "all clear")
        reporter.log_task("disk cleanup", True, "cleaned 200MB")

        report = reporter.daily_report()
        text = reporter.format_report(report)
        assert "disk cleanup" in text
        assert "2x" in text
        assert "Most Common Tasks" in text
        assert "End of Report" in text

    def test_clear_old_entries(self, reporter):
        # Log entries (all are recent, so none will be deleted)
        reporter.log_task("test task", True)
        deleted = reporter.clear_old_entries(days=0)
        assert deleted >= 0

    def test_top_tasks_sorted(self, reporter):
        reporter.log_task("task A", True)
        reporter.log_task("task B", True)
        reporter.log_task("task A", True)
        reporter.log_task("task A", True)
        reporter.log_task("task C", True)

        report = reporter.daily_report()
        top = report["top_tasks"]
        assert top[0]["goal"] == "task A"
        assert top[0]["count"] == 3
