"""Confidence Drop Anomaly Detector — monitors metacog confidence and logs to tamper-proof black box."""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConfidenceDropDetector:
    """Monitors AIOS confidence levels and detects anomalies.

    Triggers:
    - Sudden drop: confidence drops > threshold from previous assessment
    - Sustained low: confidence below threshold for N consecutive assessments
    - Alternating: confidence oscillates between high and low
    """

    def __init__(self, black_box=None, config: Dict = None):
        self.black_box = black_box
        cfg = config or {}
        self.drop_threshold = cfg.get("drop_threshold", 0.30)
        self.sustained_count = cfg.get("sustained_count", 3)
        self.low_threshold = cfg.get("low_threshold", 0.40)
        self._history: List[float] = []

    def check(self, confidence: float, context: Dict = None) -> Optional[str]:
        """Check for anomaly. Returns anomaly type or None."""
        self._history.append(confidence)

        # Sudden drop detection
        if len(self._history) >= 2:
            prev = self._history[-2]
            drop = prev - confidence
            if drop >= self.drop_threshold:
                anomaly = "confidence_drop"
                self._log_anomaly(anomaly, {
                    "previous_confidence": prev,
                    "current_confidence": confidence,
                    "drop_amount": round(drop, 3),
                    "context": context or {},
                })
                return anomaly

        # Sustained low detection
        if len(self._history) >= self.sustained_count:
            recent = self._history[-self.sustained_count:]
            if all(c < self.low_threshold for c in recent):
                anomaly = "sustained_low_confidence"
                self._log_anomaly(anomaly, {
                    "recent_confidences": recent,
                    "threshold": self.low_threshold,
                    "context": context or {},
                })
                return anomaly

        # Alternating detection (high-low-high-low pattern)
        if len(self._history) >= 4:
            recent = self._history[-4:]
            above = [c >= self.low_threshold for c in recent]
            # Check for alternating pattern: True, False, True, False or False, True, False, True
            if all(above[i] != above[i+1] for i in range(3)):
                anomaly = "alternating_confidence"
                self._log_anomaly(anomaly, {
                    "recent_confidences": recent,
                    "pattern": above,
                    "context": context or {},
                })
                return anomaly

        return None

    def _log_anomaly(self, anomaly_type: str, data: Dict) -> None:
        """Log anomaly to tamper-proof black box."""
        if not self.black_box:
            logger.warning(f"Anomaly detected [{anomaly_type}] but no black box available")
            return

        event_data = {
            "anomaly_type": anomaly_type,
            **data,
        }
        self.black_box.insert("confidence_anomaly", event_data)
        logger.info(f"Confidence anomaly logged: {anomaly_type}")

    def get_history(self) -> List[float]:
        return self._history.copy()

    def reset(self) -> None:
        self._history = []
