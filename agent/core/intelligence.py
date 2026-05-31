import os
import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class IntelligenceRule:
    id: str = ""
    name: str = ""
    trigger: str = ""
    action: str = ""
    priority: str = "medium"
    enabled: bool = True

class IntelligenceEngine:
    """Rules engine for proactive system intelligence."""

    def __init__(self, rules_path: str = None):
        self.rules: Dict[str, IntelligenceRule] = {}
        self.callbacks: Dict[str, Callable] = {}
        if rules_path and os.path.exists(rules_path):
            self.load_rules(rules_path)
        else:
            self._load_default_rules()

    def _load_default_rules(self):
        defaults = [
            IntelligenceRule("disk_cleanup", "Disk Cleanup", "disk > 80", "Clean temp files and old logs", "medium"),
            IntelligenceRule("cpu_monitor", "High CPU Monitor", "cpu > 90 for 5min", "Check process causing high CPU", "high"),
            IntelligenceRule("memory_alert", "Memory Pressure", "memory > 90", "Identify memory-heavy processes", "high"),
            IntelligenceRule("security_scan", "Periodic Security Scan", "schedule: daily", "Run security audit on running processes", "medium"),
            IntelligenceRule("log_rotation", "Log Rotation", "schedule: weekly", "Archive old log files", "low"),
        ]
        for rule in defaults:
            self.rules[rule.id] = rule

    def load_rules(self, path: str) -> None:
        with open(path, "r") as f:
            data = json.load(f)
        for item in data.get("rules", []):
            rule = IntelligenceRule(**item)
            self.rules[rule.id] = rule
        logger.info(f"Loaded {len(self.rules)} intelligence rules from {path}")

    def evaluate(self, system_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate rules against current system state. Returns list of triggered tasks."""
        triggered = []

        for rule in self.rules.values():
            if not rule.enabled:
                continue

            if self._check_trigger(rule.trigger, system_state):
                triggered.append({
                    "goal": rule.action,
                    "priority": rule.priority,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                })
                logger.info(f"Rule triggered: {rule.name} -> {rule.action}")

        return triggered

    def _check_trigger(self, trigger: str, state: Dict[str, Any]) -> bool:
        if trigger.startswith("schedule:"):
            return False  # Scheduling handled by daemon loop

        if "disk >" in trigger:
            threshold = float(trigger.split(">")[1].strip().split()[0])
            return state.get("disk_percent", 0) > threshold

        if "cpu >" in trigger:
            threshold = float(trigger.split(">")[1].strip().split()[0])
            return state.get("cpu_percent", 0) > threshold

        if "memory >" in trigger:
            threshold = float(trigger.split(">")[1].strip().split()[0])
            return state.get("memory_percent", 0) > threshold

        return False

    def add_callback(self, rule_id: str, callback: Callable) -> None:
        self.callbacks[rule_id] = callback

    def get_active_rules(self) -> List[Dict[str, Any]]:
        return [
            {"id": r.id, "name": r.name, "trigger": r.trigger, "enabled": r.enabled}
            for r in self.rules.values()
        ]
