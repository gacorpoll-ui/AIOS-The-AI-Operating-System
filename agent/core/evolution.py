"""AIOS Self-Evolution System — learns from black box data and improves itself.

Design:
- Analyzes black box history for patterns (confident actions, repeated failures)
- Generates improvement suggestions (tool optimization, rule tuning, workflow discovery)
- All evolution activity logged to black box under "SYSTEM" agent
- Human can disable entirely via config: evolution.enabled=false
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from collections import Counter

logger = logging.getLogger(__name__)


# ── YAML Parser (recursive, arbitrary nesting) ─────────────────────

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

        # Must be a key: value or key:
        if ":" not in stripped or stripped.startswith("- "):
            break

        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()

        if rest:
            # Inline value
            result[key] = _yaml_val(rest)
            i += 1
        else:
            # Check next non-empty line to determine type
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1

            if j >= len(lines) or _get_indent(lines[j]) <= indent:
                # Empty value or next line is at same/lower indent
                result[key] = None
                i += 1
            elif lines[j].strip().startswith("- "):
                # It's a list
                lst, i = _parse_list(lines, j, _get_indent(lines[j]))
                result[key] = lst
            else:
                # It's a nested dict
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
            # Dict item in list
            d = {}
            k, _, v = item.partition(":")
            d[k.strip()] = _yaml_val(v)

            # Look for more keys at deeper indent
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

    return config


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


# ── Evolution Engine ──────────────────────────────────────────────

class EvolutionEngine:
    """Self-evolution system that learns from black box data."""

    def __init__(self, config_path: str = None, black_box=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "evolution.yaml")

        self.config = _parse_yaml(config_path) if os.path.exists(config_path) else {}
        evo_cfg = self.config.get("evolution", {})
        self.enabled = evo_cfg.get("enabled", True)
        self.cycle_interval = evo_cfg.get("cycle_interval", 3600)
        self.min_assessments = evo_cfg.get("min_assessments", 50)
        self.evo_types = evo_cfg.get("types", {})
        self.safety = evo_cfg.get("safety", {})
        self.bb_cfg = evo_cfg.get("black_box", {})
        self.log_as_agent = self.bb_cfg.get("log_evolution_as", "SYSTEM")
        self.max_changes = self.safety.get("max_changes_per_cycle", 5)
        self.require_approval = self.safety.get("require_approval_for", [])

        self.black_box = black_box
        self._last_cycle = 0
        self._changes_this_cycle = 0

    def should_run(self) -> bool:
        """Check if evolution cycle should run."""
        if not self.enabled:
            return False
        now = time.time()
        return (now - self._last_cycle) >= self.cycle_interval

    def run_cycle(self, black_box_data: List[Dict], metacog_stats: Dict = None) -> Dict[str, Any]:
        """Run one evolution cycle. Returns improvements found."""
        if not self.enabled:
            return {"status": "disabled", "improvements": []}

        if len(black_box_data) < self.min_assessments:
            return {
                "status": "insufficient_data",
                "have": len(black_box_data),
                "need": self.min_assessments,
                "improvements": [],
            }

        self._last_cycle = time.time()
        self._changes_this_cycle = 0
        improvements = []

        if self.evo_types.get("tool_optimization", True):
            improvements.extend(self._optimize_tools(black_box_data))

        if self.evo_types.get("rule_tuning", True):
            improvements.extend(self._tune_rules(black_box_data))

        if self.evo_types.get("workflow_discovery", True):
            improvements.extend(self._discover_workflows(black_box_data))

        if self.evo_types.get("error_prevention", True):
            improvements.extend(self._prevent_errors(black_box_data))

        # Log evolution activity to black box under SYSTEM agent
        self._log_evolution(improvements)

        return {
            "status": "completed",
            "improvements": improvements,
            "total_changes": self._changes_this_cycle,
        }

    def _optimize_tools(self, data: List[Dict]) -> List[Dict]:
        """Find tools that are frequently used and suggest optimizations."""
        tool_usage = Counter()
        tool_failures = Counter()

        for event in data:
            e_data = event.get("data", {})
            if "tool_name" in e_data:
                tool_usage[e_data["tool_name"]] += 1
                if not e_data.get("success", True):
                    tool_failures[e_data["tool_name"]] += 1

        improvements = []
        for tool, count in tool_usage.most_common(5):
            failures = tool_failures.get(tool, 0)
            fail_rate = failures / count if count > 0 else 0

            if fail_rate > 0.3 and count >= 10:
                improvements.append({
                    "type": "tool_optimization",
                    "tool": tool,
                    "suggestion": f"High failure rate ({fail_rate:.0%}) — add error handling or user confirmation",
                    "requires_approval": True,
                    "confidence": 0.75,
                })

        return improvements

    def _tune_rules(self, data: List[Dict]) -> List[Dict]:
        """Suggest threshold adjustments based on confidence patterns."""
        confidences = []
        for event in data:
            e_data = event.get("data", {})
            if "confidence" in e_data:
                confidences.append(e_data["confidence"])

        if not confidences:
            return []

        avg_conf = sum(confidences) / len(confidences)

        # If average confidence is consistently high, suggest raising threshold
        improvements = []
        if avg_conf > 0.85:
            improvements.append({
                "type": "rule_tuning",
                "suggestion": f"Average confidence is {avg_conf:.0%} — consider raising metacog threshold from 0.65 to 0.70",
                "requires_approval": True,
                "confidence": 0.60,
            })
        elif avg_conf < 0.40:
            improvements.append({
                "type": "rule_tuning",
                "suggestion": f"Average confidence is {avg_conf:.0%} — consider lowering threshold or improving tool reliability",
                "requires_approval": True,
                "confidence": 0.65,
            })

        return improvements

    def _discover_workflows(self, data: List[Dict]) -> List[Dict]:
        """Find common tool sequences that could become automated workflows."""
        # Simple pattern: find tools that are often used together
        tool_cooccurrence = Counter()
        seen_tools = set()

        for event in data:
            e_data = event.get("data", {})
            if "tool_name" in e_data:
                tool = e_data["tool_name"]
                for seen in seen_tools:
                    pair = tuple(sorted([seen, tool]))
                    tool_cooccurrence[pair] += 1
                seen_tools.add(tool)

        improvements = []
        for (t1, t2), count in tool_cooccurrence.most_common(3):
            if count >= 5:
                improvements.append({
                    "type": "workflow_discovery",
                    "suggestion": f"Tools '{t1}' and '{t2}' used together {count} times — consider creating automated workflow",
                    "requires_approval": True,
                    "confidence": 0.55,
                })

        return improvements

    def _prevent_errors(self, data: List[Dict]) -> List[Dict]:
        """Learn from past failures and suggest prevention measures."""
        error_patterns = Counter()

        for event in data:
            e_type = event.get("event_type", "")
            e_data = event.get("data", {})

            if "anomaly" in e_type.lower() or not e_data.get("success", True):
                tool = e_data.get("tool_name", "unknown")
                error_msg = e_data.get("error", e_data.get("drop_amount", ""))
                pattern = f"{tool}:{str(error_msg)[:30]}"
                error_patterns[pattern] += 1

        improvements = []
        for pattern, count in error_patterns.most_common(3):
            if count >= 2:
                improvements.append({
                    "type": "error_prevention",
                    "suggestion": f"Recurring error pattern '{pattern}' ({count}x) — add pre-flight check",
                    "requires_approval": False,
                    "confidence": 0.80,
                })
                self._changes_this_cycle += 1

        return improvements

    def _log_evolution(self, improvements: List[Dict]) -> None:
        """Log all evolution activity to black box under SYSTEM agent."""
        if not self.black_box:
            logger.warning("Evolution activity not logged — no black box available")
            return

        self.black_box.insert("evolution_activity", {
            "agent": self.log_as_agent,
            "type": "evolution_cycle",
            "improvements_count": len(improvements),
            "improvements": json.dumps(improvements),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_config(self) -> Dict[str, Any]:
        """Return current evolution config."""
        return {
            "enabled": self.enabled,
            "cycle_interval": self.cycle_interval,
            "min_assessments": self.min_assessments,
            "max_changes_per_cycle": self.max_changes,
            "log_as": self.log_as_agent,
        }

    def disable(self) -> None:
        """Disable evolution (human override)."""
        self.enabled = False
        logger.info("Evolution DISABLED by human operator")
        if self.black_box:
            self.black_box.insert("evolution_activity", {
                "agent": self.log_as_agent,
                "type": "evolution_disabled",
                "reason": "human_override",
            })

    def enable(self) -> None:
        """Re-enable evolution."""
        self.enabled = True
        logger.info("Evolution ENABLED by human operator")
        if self.black_box:
            self.black_box.insert("evolution_activity", {
                "agent": self.log_as_agent,
                "type": "evolution_enabled",
                "reason": "human_override",
            })
