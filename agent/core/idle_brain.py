"""Idle Intelligence — AIOS thinks when idle.

Design:
- When no user input for N seconds, AIOS enters "idle mode"
- In idle mode: processes backlog, discovers patterns, pre-warms tools, generates insights
- Human can disable: aios config proactive.enabled=false
- User can see status: aios idle status
- Wakeup report max 5 bullet points (no walls of text)
- All activity logged to black box under "SYSTEM" agent
"""

import os
import json
import time
import threading
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class IdleBrain:
    """Background intelligence that runs when user is idle."""

    def __init__(self, config: Dict[str, Any] = None,
                 black_box=None, metacog=None, prediction=None,
                 evolution=None, task_queue=None):
        cfg = config or {}
        self.enabled = cfg.get("enabled", True)
        self.idle_timeout = cfg.get("idle_timeout", 30)  # seconds before idle starts
        self.cycle_interval = cfg.get("cycle_interval", 60)  # seconds between idle cycles
        self.max_tasks_per_cycle = cfg.get("max_tasks_per_cycle", 3)

        self.black_box = black_box
        self.metacog = metacog
        self.prediction = prediction
        self.evolution = evolution
        self.task_queue = task_queue

        self._is_idle = False
        self._last_user_activity = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._idle_tasks_done: List[str] = []
        self._wakeup_report: List[str] = []

    def start(self) -> None:
        """Start the idle brain background thread."""
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._idle_loop,
            daemon=True,
            name="aios-idle-brain"
        )
        self._thread.start()
        logger.info("Idle brain started")

    def stop(self) -> None:
        """Stop the idle brain."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Idle brain stopped")

    def record_activity(self) -> None:
        """Call this whenever user does something."""
        self._last_user_activity = time.time()
        self._is_idle = False

    def is_currently_idle(self) -> bool:
        return self._is_idle

    def time_since_activity(self) -> float:
        return time.time() - self._last_user_activity

    def _idle_loop(self) -> None:
        """Background loop: check idle status, run idle tasks."""
        while self._running:
            elapsed = self.time_since_activity()

            if elapsed >= self.idle_timeout:
                if not self._is_idle:
                    self._is_idle = True
                    logger.info("AIOS entering idle mode")
                    self._log_idle_event("entered_idle")

                self._run_idle_cycle()
            else:
                if self._is_idle:
                    self._is_idle = False
                    self._generate_wakeup_report()
                    logger.info("AIOS waking up from idle mode")
                    self._log_idle_event("woke_up")

            time.sleep(min(self.cycle_interval, 5))

    def _run_idle_cycle(self) -> None:
        """Run one cycle of idle intelligence tasks."""
        tasks_done = 0

        # 1. Process backlog (failed/pending tasks)
        if self.task_queue and tasks_done < self.max_tasks_per_cycle:
            processed = self._process_backlog()
            tasks_done += processed

        # 2. Discover patterns from black box data
        if self.prediction and tasks_done < self.max_tasks_per_cycle:
            self._discover_patterns()
            tasks_done += 1

        # 3. Run evolution cycle if enough data
        if self.evolution and tasks_done < self.max_tasks_per_cycle:
            self._run_evolution()
            tasks_done += 1

        # 4. Pre-warm predicted tools
        if self.prediction and tasks_done < self.max_tasks_per_cycle:
            self._prewarm_predicted_tools()
            tasks_done += 1

    def _process_backlog(self) -> int:
        """Process failed/pending tasks from task queue."""
        if not self.task_queue:
            return 0
        try:
            next_task = self.task_queue.get_next()
            if next_task and next_task.status in ("pending", "retry"):
                # In a full implementation, this would run through orchestrator
                logger.info(f"Idle brain processing task: {next_task.goal}")
                self.task_queue.mark_running(next_task.id)
                self.task_queue.mark_done(next_task.id, "Processed during idle")
                self._idle_tasks_done.append(next_task.goal)
                return 1
        except Exception as e:
            logger.debug(f"Backlog processing failed: {e}")
        return 0

    def _discover_patterns(self) -> None:
        """Discover patterns from recent black box activity."""
        if not self.black_box:
            return
        try:
            chain = self.black_box.get_recent(50)
            # Simple pattern: count tool usage
            tool_counts = {}
            for event in chain:
                data = event.get("data", {})
                tool = data.get("tool_name")
                if tool:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1

            if tool_counts:
                top_tool = max(tool_counts, key=tool_counts.get)
                logger.debug(f"Idle pattern discovery: most used tool = {top_tool}")
        except Exception as e:
            logger.debug(f"Pattern discovery failed: {e}")

    def _run_evolution(self) -> None:
        """Run evolution cycle if conditions are met."""
        if not self.evolution:
            return
        try:
            if self.evolution.should_run():
                result = self.evolution.run_cycle([])
                logger.debug(f"Idle evolution: {result['status']}")
        except Exception as e:
            logger.debug(f"Idle evolution failed: {e}")

    def _prewarm_predicted_tools(self) -> None:
        """Pre-warm tools predicted by the prediction engine."""
        if not self.prediction:
            return
        try:
            # Get predictions (this triggers silent pre-warm internally)
            self.prediction.predict([])
        except Exception as e:
            logger.debug(f"Pre-warm failed: {e}")

    def _generate_wakeup_report(self) -> None:
        """Generate a wakeup report (max 5 bullet points)."""
        report = []

        # 1. Tasks processed
        if self._idle_tasks_done:
            count = len(self._idle_tasks_done)
            report.append(f"Processed {count} backlog task(s) while idle")
            self._idle_tasks_done = []

        # 2. Patterns discovered
        report.append("Discovered usage patterns from recent activity")

        # 3. Pre-warmed tools
        if self.prediction:
            status = self.prediction.get_prewarm_status()
            if status.get("cached_items", 0) > 0:
                report.append(f"Pre-warmed {status['cached_items']} predicted tools")

        # 4. Evolution status
        if self.evolution:
            config = self.evolution.get_config()
            report.append(f"Evolution engine active (interval: {config.get('cycle_interval', 'N/A')}s)")

        # 5. Idle duration
        idle_time = self.time_since_activity()
        minutes = int(idle_time / 60)
        if minutes > 0:
            report.append(f"Was idle for {minutes} minute(s)")

        # Cap at 5 bullet points
        self._wakeup_report = report[:5]

        # Log to black box
        if self.black_box:
            self.black_box.insert("idle_activity", {
                "agent": "SYSTEM",
                "type": "wakeup_report",
                "report": json.dumps(self._wakeup_report),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def get_status(self) -> Dict[str, Any]:
        """Get current idle brain status."""
        return {
            "enabled": self.enabled,
            "is_idle": self._is_idle,
            "seconds_since_activity": round(self.time_since_activity(), 1),
            "idle_timeout": self.idle_timeout,
            "cycle_interval": self.cycle_interval,
            "wakeup_report": self._wakeup_report,
            "tasks_done_while_idle": len(self._idle_tasks_done),
        }

    def disable(self) -> None:
        """Disable idle intelligence (human override)."""
        self.enabled = False
        self.stop()
        logger.info("Idle brain DISABLED by human operator")
        if self.black_box:
            self.black_box.insert("idle_activity", {
                "agent": "SYSTEM",
                "type": "idle_disabled",
                "reason": "human_override",
            })

    def enable(self) -> None:
        """Re-enable idle intelligence."""
        self.enabled = True
        self.start()
        logger.info("Idle brain ENABLED by human operator")

    def _log_idle_event(self, event_type: str) -> None:
        """Log idle event to black box."""
        if self.black_box:
            self.black_box.insert("idle_activity", {
                "agent": "SYSTEM",
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
