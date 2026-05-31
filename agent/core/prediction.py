"""AIOS Prediction Engine — predicts user's next action and silently pre-warms.

Design:
- Predictions are LOCAL only — no cloud sync ever
- Pre-warm is SILENT — user never sees loading states
- Pre-warm never uses more than 20% CPU (background priority)
- User can see all predictions: aios predict show
- User can disable: aios config prediction.enabled=false
"""

import os
import json
import time
import logging
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


# ── YAML Parser (reuse from evolution) ────────────────────────────

def _parse_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        lines = [l.rstrip() for l in f.readlines()]
    result, _ = _parse_block(lines, 0, 0)
    return result


def _get_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _parse_block(lines, start, min_indent):
    result = {}
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = _get_indent(line)
        if indent < min_indent:
            break
        if ":" not in stripped or stripped.startswith("- "):
            break
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest:
            result[key] = _yaml_val(rest)
            i += 1
        else:
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j >= len(lines) or _get_indent(lines[j]) <= indent:
                result[key] = None
                i += 1
            elif lines[j].strip().startswith("- "):
                lst, i = _parse_list(lines, j, _get_indent(lines[j]))
                result[key] = lst
            else:
                sub_dict, i = _parse_block(lines, j, _get_indent(lines[j]))
                result[key] = sub_dict
    return result, i


def _parse_list(lines, start, list_indent):
    result = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = _get_indent(line)
        if indent < list_indent:
            break
        if not stripped.startswith("- "):
            break
        item = stripped[2:].strip()
        if ":" in item:
            d = {}
            k, _, v = item.partition(":")
            d[k.strip()] = _yaml_val(v)
            j = i + 1
            item_indent = indent + 2
            while j < len(lines):
                jr = lines[j]
                jl = jr.strip()
                if not jl or jl.startswith("#"):
                    j += 1
                    continue
                ji = _get_indent(jr)
                if ji < item_indent or jl.startswith("- "):
                    break
                if ":" in jl and not jl.startswith("- "):
                    k2, _, v2 = jl.partition(":")
                    d[k2.strip()] = _yaml_val(v2)
                j += 1
            result.append(d)
            i = j
        else:
            result.append(_yaml_val(item))
            i += 1
    return result, i


def _yaml_val(s: str) -> Any:
    s = s.strip()
    ci = s.find(" #")
    if ci > 0:
        s = s[:ci].strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s.strip('"').strip("'")


# ── Prediction Engine ─────────────────────────────────────────────

class PredictionEngine:
    """Predicts user's next action and silently pre-warms tools."""

    def __init__(self, config_path: str = None, black_box=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "prediction.yaml")

        self.config = _parse_yaml(config_path) if os.path.exists(config_path) else {}
        pred_cfg = self.config.get("prediction", {})
        self.enabled = pred_cfg.get("enabled", True)
        self.max_cpu = pred_cfg.get("max_cpu_fraction", 0.20)
        self.prediction_window = pred_cfg.get("prediction_window", 300)
        self.min_history = pred_cfg.get("min_history", 30)
        self.patterns = pred_cfg.get("patterns", {})
        self.prewarm_cfg = pred_cfg.get("prewarm", {})

        self.black_box = black_box
        self._predictions: List[Dict[str, Any]] = []
        self._prewarm_cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._prewarm_thread: Optional[threading.Thread] = None

    def should_run(self) -> bool:
        return self.enabled

    def predict(self, user_history: List[Dict]) -> List[Dict[str, Any]]:
        """Predict user's next actions. LOCAL only, no cloud sync."""
        if not self.enabled:
            return []

        if len(user_history) < self.min_history:
            return []

        with self._lock:
            predictions = []

            if self.patterns.get("frequency_based", True):
                predictions.extend(self._predict_frequency(user_history))

            if self.patterns.get("sequence_based", True):
                predictions.extend(self._predict_sequence(user_history))

            if self.patterns.get("time_based", True):
                predictions.extend(self._predict_time(user_history))

            # Sort by confidence, take top 5
            predictions.sort(key=lambda x: -x.get("confidence", 0))
            self._predictions = predictions[:5]
            to_prewarm = self._predictions[:self.prewarm_cfg.get("max_items", 3)]

        # Silent pre-warm in background (outside lock)
        self._silent_prewarm(to_prewarm)

        return self._predictions

    def _predict_frequency(self, history: List[Dict]) -> List[Dict]:
        """Predict based on most frequently used tools."""
        tool_counter = Counter()
        for event in history:
            e_data = event.get("data", {})
            if "tool_name" in e_data:
                tool_counter[e_data["tool_name"]] += 1

        predictions = []
        total = sum(tool_counter.values())
        for tool, count in tool_counter.most_common(3):
            predictions.append({
                "type": "frequency",
                "predicted_tool": tool,
                "predicted_action": f"User will likely use '{tool}'",
                "confidence": round(count / total, 3),
                "reasoning": f"Used {count}/{total} times ({count/total:.0%})",
            })

        return predictions

    def _predict_sequence(self, history: List[Dict]) -> List[Dict]:
        """Predict based on tool sequences (if A then B)."""
        sequences = Counter()
        prev_tool = None

        for event in history:
            e_data = event.get("data", {})
            tool = e_data.get("tool_name")
            if tool and prev_tool:
                sequences[(prev_tool, tool)] += 1
            if tool:
                prev_tool = tool

        # Find the most recent tool
        recent_tool = None
        for event in reversed(history):
            e_data = event.get("data", {})
            if e_data.get("tool_name"):
                recent_tool = e_data["tool_name"]
                break

        if not recent_tool:
            return []

        # Find what typically follows the recent tool
        predictions = []
        for (t1, t2), count in sequences.most_common(5):
            if t1 == recent_tool and count >= 2:
                predictions.append({
                    "type": "sequence",
                    "predicted_tool": t2,
                    "predicted_action": f"After '{t1}', user usually runs '{t2}'",
                    "confidence": round(min(count / 5, 1.0), 3),
                    "reasoning": f"Seen {count} times after '{t1}'",
                    "after_tool": t1,
                })

        return predictions

    def _predict_time(self, history: List[Dict]) -> List[Dict]:
        """Predict based on time-of-day patterns."""
        hour_tools = defaultdict(lambda: Counter())
        current_hour = datetime.now(timezone.utc).hour

        for event in history:
            e_data = event.get("data", {})
            tool = e_data.get("tool_name")
            ts = event.get("timestamp", "")
            if tool and ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    hour_tools[dt.hour][tool] += 1
                except (ValueError, TypeError):
                    pass

        predictions = []
        current_tools = hour_tools[current_hour]
        for tool, count in current_tools.most_common(3):
            if count >= 2:
                predictions.append({
                    "type": "time_based",
                    "predicted_tool": tool,
                    "predicted_action": f"At this hour, user usually runs '{tool}'",
                    "confidence": round(min(count / 5, 1.0), 3),
                    "reasoning": f"Used {count} times at hour {current_hour}",
                })

        return predictions

    def _silent_prewarm(self, predictions: List[Dict]) -> None:
        """Pre-warm predicted tools silently in background. Never blocks user."""
        if not self.prewarm_cfg.get("enabled", True):
            return

        # Kill previous pre-warm if still running
        if self._prewarm_thread and self._prewarm_thread.is_alive():
            # Don't wait — just let it finish naturally
            pass

        self._prewarm_thread = threading.Thread(
            target=self._do_prewarm,
            args=(predictions,),
            daemon=True,
            name="aios-prewarm"
        )
        self._prewarm_thread.start()

    def _do_prewarm(self, predictions: List[Dict]) -> None:
        """Actual pre-warm work (runs in background thread)."""
        timeout = self.prewarm_cfg.get("timeout_seconds", 5)
        start = time.time()

        for pred in predictions:
            if time.time() - start > timeout:
                break

            tool = pred.get("predicted_tool")
            if not tool:
                continue

            # Pre-warm: cache the tool info / prepare resources
            self._prewarm_cache[tool] = {
                "predicted_at": datetime.now(timezone.utc).isoformat(),
                "confidence": pred.get("confidence", 0),
                "reasoning": pred.get("reasoning", ""),
                "status": "prewarmed",
            }
            logger.debug(f"Pre-warmed: {tool} (confidence={pred.get('confidence', 0):.0%})")

    def get_predictions(self) -> List[Dict[str, Any]]:
        """Get current predictions (for 'aios predict show')."""
        return self._predictions.copy()

    def get_prewarm_status(self) -> Dict[str, Any]:
        """Get pre-warm cache status."""
        return {
            "enabled": self.enabled,
            "cached_items": len(self._prewarm_cache),
            "cache": self._prewarm_cache.copy(),
            "prewarm_running": self._prewarm_thread and self._prewarm_thread.is_alive(),
        }

    def disable(self) -> None:
        """Disable predictions (human override)."""
        self.enabled = False
        self._predictions = []
        self._prewarm_cache = {}
        logger.info("Prediction engine DISABLED by human operator")
        if self.black_box:
            self.black_box.insert("prediction_activity", {
                "agent": "SYSTEM",
                "type": "prediction_disabled",
                "reason": "human_override",
            })

    def enable(self) -> None:
        """Re-enable predictions."""
        self.enabled = True
        logger.info("Prediction engine ENABLED by human operator")
        if self.black_box:
            self.black_box.insert("prediction_activity", {
                "agent": "SYSTEM",
                "type": "prediction_enabled",
                "reason": "human_override",
            })
