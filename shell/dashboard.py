"""AIOS CLI Dashboard — real-time terminal UI showing all systems at a glance.

Full-screen dashboard using rich library. Refreshes every 2 seconds.
Command: aios dashboard
Controls: q=exit, p=pause, e=expand panel
Works in 80-column terminals minimum.
"""

import os
import sys
import time
import json
import threading
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

try:
    from rich.console import Console
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Status Snapshot
# ═══════════════════════════════════════════════════════════════════

@dataclass
class StatusSnapshot:
    """Aggregated status from all AIOS subsystems."""
    timestamp: str = ""
    # System health
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    disk_percent: float = 0.0
    uptime_seconds: int = 0
    # AI status
    llm_loaded: bool = False
    llm_model: str = ""
    metacog_active: bool = False
    metacog_confidence: float = 0.0
    # Agents
    orchestrator_status: str = "idle"    # idle, running, error
    predictor_status: str = "idle"
    evolution_status: str = "idle"
    parliament_status: str = "ready"
    # Predictions
    next_prediction: str = ""
    prediction_in_seconds: int = 0
    prediction_confidence: float = 0.0
    # Constitution/Blackbox
    constitution_sealed: bool = True
    blackbox_integrity: str = "INTACT"
    blackbox_events: int = 0
    # Recent actions
    recent_actions: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "llm_model": self.llm_model,
            "orchestrator_status": self.orchestrator_status,
            "constitution_sealed": self.constitution_sealed,
            "blackbox_integrity": self.blackbox_integrity,
        }


# ═══════════════════════════════════════════════════════════════════
# Status Reporter
# ═══════════════════════════════════════════════════════════════════

class StatusReporter:
    """Collects status from all subsystems via IPC or direct access."""

    def __init__(self, components: Dict[str, Any] = None):
        self.components = components or {}

    def get_snapshot(self) -> StatusSnapshot:
        """Collect current status from all subsystems."""
        snapshot = StatusSnapshot()
        snapshot.timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        # System health (psutil)
        try:
            import psutil
            snapshot.cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            snapshot.ram_percent = mem.percent
            snapshot.ram_used_gb = round(mem.used / (1024**3), 1)
            snapshot.disk_percent = psutil.disk_usage('/').percent
            snapshot.uptime_seconds = int(time.time() - psutil.boot_time())
        except ImportError:
            pass

        # AI components
        llm = self.components.get("llm")
        if llm:
            snapshot.llm_loaded = getattr(llm, "is_loaded", False)
            if hasattr(llm, "model_info"):
                snapshot.llm_model = llm.model_info.get("model", llm.model_info.get("name", ""))

        metacog = self.components.get("metacog")
        if metacog:
            snapshot.metacog_active = True

        # Agent statuses
        orchestrator = self.components.get("orchestrator")
        if orchestrator:
            snapshot.orchestrator_status = "ready"

        predictor = self.components.get("prediction")
        if predictor:
            snapshot.predictor_status = "running"
            preds = predictor.get_predictions()
            if preds:
                snapshot.next_prediction = preds[0].get("predicted_action", "")
                snapshot.prediction_confidence = preds[0].get("confidence", 0)

        evolution = self.components.get("evolution")
        if evolution:
            snapshot.evolution_status = "active" if evolution.enabled else "disabled"

        # Constitution
        constitution = self.components.get("constitution")
        if constitution:
            snapshot.constitution_sealed = getattr(constitution, "_sealed", True)

        # Black box
        black_box = self.components.get("black_box")
        if black_box:
            try:
                integrity = black_box.verify_integrity()
                snapshot.blackbox_integrity = integrity.get("integrity", "UNKNOWN")
                snapshot.blackbox_events = integrity.get("total_events", 0)
            except Exception:
                snapshot.blackbox_integrity = "ERROR"

        # Recent actions (from black box)
        if black_box:
            try:
                chain = black_box.get_recent(5)
                snapshot.recent_actions = [
                    {
                        "time": e.get("timestamp", "")[-8:],
                        "action": f"{e.get('event_type', '')}: {str(e.get('data', {}).get('tool_name', e.get('data', {}).get('task_goal', '')))[:40]}",
                    }
                    for e in chain
                ]
            except Exception:
                pass

        return snapshot

    def get_one_line_status(self) -> str:
        """Get a one-line summary for 'aios status' command."""
        snapshot = self.get_snapshot()
        status_parts = []

        # AI status
        if snapshot.llm_loaded:
            status_parts.append(f"AI: {snapshot.llm_model or 'loaded'}")
        else:
            status_parts.append("AI: not loaded")

        # System
        status_parts.append(f"CPU: {snapshot.cpu_percent:.0f}%")
        status_parts.append(f"RAM: {snapshot.ram_used_gb}GB")

        # Constitution
        c_status = "[OK]" if snapshot.constitution_sealed else "[!]"
        status_parts.append(f"Constitution: {c_status}")

        # Black box
        bb_status = f"[{snapshot.blackbox_integrity}]"
        status_parts.append(f"BlackBox: {bb_status}")

        return " | ".join(status_parts)


# ═══════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════

class Dashboard:
    """Real-time full-screen terminal dashboard."""

    def __init__(self, reporter: StatusReporter, refresh_rate: float = 2.0):
        self.reporter = reporter
        self.refresh_rate = refresh_rate
        self.paused = False
        self.expanded_panel = None
        self.console = Console()
        self._running = False

    def _color_percent(self, value: float, warn: float = 70, crit: float = 90) -> str:
        """Color code a percentage value."""
        if value >= crit:
            return f"[bold red]{value:.0f}%[/]"
        elif value >= warn:
            return f"[bold yellow]{value:.0f}%[/]"
        else:
            return f"[bold green]{value:.0f}%[/]"

    def _status_icon(self, status: str) -> str:
        """Return colored status indicator."""
        icons = {
            "idle": "[dim grey]○[/] idle",
            "running": "[green]●[/] running",
            "active": "[green]●[/] active",
            "ready": "[green]●[/] ready",
            "error": "[red]●[/] error",
            "disabled": "[yellow]●[/] disabled",
        }
        return icons.get(status, f"[grey]{status}[/]")

    def _build_system_health(self, snapshot: StatusSnapshot) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim", width=12)
        table.add_column("Value")

        uptime = snapshot.uptime_seconds
        hours = uptime // 3600
        mins = (uptime % 3600) // 60
        uptime_str = f"{hours}h {mins}m" if uptime > 0 else "N/A"

        table.add_row("CPU", self._color_percent(snapshot.cpu_percent))
        table.add_row("RAM", f"{self._color_percent(snapshot.ram_percent)} ({snapshot.ram_used_gb}GB)")
        table.add_row("Disk", self._color_percent(snapshot.disk_percent, warn=80, crit=95))
        table.add_row("Uptime", uptime_str)
        table.add_row("LLM", "[green]loaded[/]" if snapshot.llm_loaded else "[yellow]not loaded[/]")

        return Panel(table, title="[bold cyan]SYSTEM HEALTH[/]", border_style="cyan")

    def _build_active_agents(self, snapshot: StatusSnapshot) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Agent", style="dim", width=16)
        table.add_column("Status")

        table.add_row("Orchestrator", self._status_icon(snapshot.orchestrator_status))
        table.add_row("Metacog", self._status_icon("active" if snapshot.metacog_active else "idle"))
        table.add_row("Predictor", self._status_icon(snapshot.predictor_status))
        table.add_row("Evolution", self._status_icon(snapshot.evolution_status))
        table.add_row("Parliament", self._status_icon(snapshot.parliament_status))

        return Panel(table, title="[bold cyan]ACTIVE AGENTS[/]", border_style="cyan")

    def _build_recent_actions(self, snapshot: StatusSnapshot) -> Panel:
        table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
        table.add_column("Time", style="dim", width=8)
        table.add_column("Action")

        actions = snapshot.recent_actions or [{"time": "--:--", "action": "No actions yet"}]
        for action in actions[:5]:
            table.add_row(action.get("time", "--:--"), action.get("action", ""))

        return Panel(table, title="[bold cyan]RECENT ACTIONS[/]", border_style="cyan")

    def _build_predictions(self, snapshot: StatusSnapshot) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim", width=12)
        table.add_column("Value")

        if snapshot.next_prediction:
            table.add_row("Next", snapshot.next_prediction[:40])
            table.add_row("In", f"~{snapshot.prediction_in_seconds}s ({snapshot.prediction_confidence:.0%})")
            table.add_row("Status", "[green]Pre-warming...[/]")
        else:
            table.add_row("Status", "[dim]No active predictions[/]")
            table.add_row("", "[dim]Waiting for patterns...[/]")

        return Panel(table, title="[bold cyan]PREDICTIONS[/]", border_style="cyan")

    def _build_footer(self, snapshot: StatusSnapshot) -> Panel:
        items = []

        # Constitution
        c_icon = "[green]✓[/]" if snapshot.constitution_sealed else "[red]✗[/]"
        items.append(f"Constitution: {c_icon}")

        # Evolution
        e_icon = "[green]✓[/]" if snapshot.evolution_status == "active" else "[yellow]○[/]"
        items.append(f"Evolution: {e_icon}")

        # Black Box
        bb_ok = "INTACT" in snapshot.blackbox_integrity
        bb_icon = "[green]✓[/]" if bb_ok else "[red]✗[/]"
        items.append(f"BlackBox: {bb_icon} ({snapshot.blackbox_events} events)")

        footer_text = "  |  ".join(items)
        return Panel(f"[bold]{footer_text}[/]", box=box.HORIZONTALS)

    def _build_layout(self, snapshot: StatusSnapshot) -> Layout:
        layout = Layout()
        layout.split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["left"].split_column(
            Layout(self._build_system_health(snapshot), ratio=1),
            Layout(self._build_recent_actions(snapshot), ratio=1),
        )
        layout["right"].split_column(
            Layout(self._build_active_agents(snapshot), ratio=1),
            Layout(self._build_predictions(snapshot), ratio=1),
        )

        # Add footer
        body = layout
        body.split_column(
            Layout(body),
            Layout(self._build_footer(snapshot), size=3),
        )

        return layout

    def run(self) -> None:
        """Start the dashboard live view."""
        if not RICH_AVAILABLE:
            self.console.print("[red]Rich library required for dashboard.[/]")
            self.console.print("[dim]Install with: pip install rich[/]")
            return

        self._running = True
        self.console.print("[dim]Dashboard started. Press Ctrl+C or 'q' to exit.[/]\n")

        with Live(auto_refresh=False, console=self.console, screen=True) as live:
            while self._running:
                try:
                    if not self.paused:
                        snapshot = self.reporter.get_snapshot()
                        layout = self._build_layout(snapshot)
                        live.update(layout)
                    live.refresh()
                    time.sleep(self.refresh_rate)
                except KeyboardInterrupt:
                    break

        self._running = False
        self.console.print("\n[dim]Dashboard closed.[/]")


def create_dashboard(components: Dict = None, refresh_rate: float = 2.0) -> Dashboard:
    """Create a dashboard with optional component connections."""
    reporter = StatusReporter(components=components or {})
    return Dashboard(reporter=reporter, refresh_rate=refresh_rate)
