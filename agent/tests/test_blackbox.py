import pytest
import os
import gzip
import sqlite3
from agent.core.blackbox import TamperProofBlackBox
from agent.core.anomaly_detector import ConfidenceDropDetector


class TestTamperProofBlackBox:

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    def test_insert_returns_hash(self, bb):
        h = bb.insert("test_event", {"key": "value"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex length

    def test_insert_only_enforcement(self, bb):
        bb.insert("event1", {"a": 1})
        with sqlite3.connect(bb._current_db) as conn:
            with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)) as exc_info:
                conn.execute("DELETE FROM events WHERE id=1")
            assert "BLACKBOX VIOLATION" in str(exc_info.value)

    def test_update_also_blocked(self, bb):
        bb.insert("event1", {"a": 1})
        with sqlite3.connect(bb._current_db) as conn:
            with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)) as exc_info:
                conn.execute("UPDATE events SET data_json='{}' WHERE id=1")
            assert "BLACKBOX VIOLATION" in str(exc_info.value)

    def test_hash_chain_integrity(self, bb):
        bb.insert("event1", {"a": 1})
        bb.insert("event2", {"b": 2})
        bb.insert("event3", {"c": 3})

        result = bb.verify_integrity()
        assert result["integrity"] == "INTACT"
        assert result["total_events"] == 3
        assert result["tampered_ids"] == []

    def test_tamper_detection(self, bb):
        bb.insert("event1", {"a": 1})
        bb.insert("event2", {"b": 2})

        # Simulate tampering by dropping triggers and modifying data
        db_path = bb._current_db
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TRIGGER prevent_update")
            conn.execute("UPDATE events SET data_json='tampered' WHERE id=1")
            conn.commit()

        result = bb.verify_integrity()
        assert "TAMPERED" in result["integrity"]
        assert len(result["tampered_ids"]) > 0

    def test_get_chain_returns_chronological(self, bb):
        bb.insert("first", {"n": 1})
        bb.insert("second", {"n": 2})
        bb.insert("third", {"n": 3})

        chain = bb.get_chain(10)
        assert len(chain) == 3
        assert chain[0]["data"]["n"] == 1
        assert chain[1]["data"]["n"] == 2
        assert chain[2]["data"]["n"] == 3

    def test_get_archives_empty(self, bb):
        assert bb.get_archives() == []

    def test_compress_and_archive(self, tmp_path):
        bb = TamperProofBlackBox(db_dir=str(tmp_path / "bb2"))
        bb.insert("event", {"test": True})

        # Manually compress old DB to simulate rotation
        old_db = bb._current_db
        bb._compress_old_db(old_db)

        archives = bb.get_archives()
        assert len(archives) >= 1
        assert archives[0].endswith(".gz")

        # Clean up
        for a in bb.get_archives():
            os.remove(a)


class TestConfidenceDropDetector:

    @pytest.fixture
    def detector(self, bb):
        return ConfidenceDropDetector(black_box=bb)

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb3"))

    def test_sudden_drop_detected(self, detector):
        detector.check(0.90)
        anomaly = detector.check(0.40)  # drop of 0.50
        assert anomaly == "confidence_drop"

    def test_no_anomaly_for_small_change(self, detector):
        detector.check(0.80)
        anomaly = detector.check(0.75)  # drop of 0.05
        assert anomaly is None

    def test_sustained_low_detected(self, detector):
        detector.check(0.30)
        detector.check(0.25)
        anomaly = detector.check(0.20)  # 3rd consecutive below threshold
        assert anomaly == "sustained_low_confidence"

    def test_alternating_detected(self, detector):
        # Alternating: just above and just below threshold, with small steps
        # low_threshold = 0.40, drop_threshold = 0.30
        detector.check(0.45)  # True (above 0.40)
        detector.check(0.35)  # False (below 0.40), drop=0.10 (not enough for sudden_drop)
        detector.check(0.48)  # True, change=0.13 (not sudden drop)
        anomaly = detector.check(0.32)  # False, change=0.16 → alternating pattern
        assert anomaly == "alternating_confidence"

    def test_anomaly_logged_to_black_box(self, detector, bb):
        detector.check(0.90)
        detector.check(0.40)  # triggers drop

        chain = bb.get_chain(10)
        assert len(chain) >= 1
        assert chain[0]["event_type"] == "confidence_anomaly"
        assert chain[0]["data"]["anomaly_type"] == "confidence_drop"

    def test_no_black_box_still_detects(self, tmp_path):
        det = ConfidenceDropDetector(black_box=None)
        det.check(0.90)
        anomaly = det.check(0.40)
        assert anomaly == "confidence_drop"

    def test_reset_clears_history(self, detector):
        detector.check(0.90)
        detector.check(0.40)
        detector.reset()
        # After reset, history is empty so no sudden drop
        anomaly = detector.check(0.30)
        assert anomaly is None

    def test_get_history(self, detector):
        detector.check(0.90)
        detector.check(0.80)
        assert detector.get_history() == [0.90, 0.80]
