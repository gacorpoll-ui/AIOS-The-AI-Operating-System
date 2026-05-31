import time
import threading
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class SecurityDecision:
    allowed: bool
    reason: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

@dataclass
class ThreatAssessment:
    is_threat: bool
    threat_type: str
    confidence: float
    details: str

class SecurityMonitor:
    """Background monitor that evaluates system actions for security threats."""
    
    def __init__(self):
        self._running = False
        self._thread = None
        self._threat_log: List[Dict[str, Any]] = []
        self._action_history: List[Dict[str, Any]] = []
        
        # Simple heuristics for testing
        self.dangerous_tools = ["run_command", "write_file", "kill_process"]
        self.suspicious_paths = [r"(?i)\.ssh", r"(?i)/etc/shadow", r"(?i)/etc/passwd", r"(?i)system32"]
        
    def start(self) -> None:
        """Starts background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("SecurityMonitor started")
        
    def stop(self) -> None:
        """Stops background monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("SecurityMonitor stopped")
        
    def _monitor_loop(self) -> None:
        while self._running:
            # In a full implementation, this would continuously evaluate
            # the _action_history buffer to detect sequences like 
            # "read file" -> "send network request" (exfiltration)
            if len(self._action_history) > 10:
                self.analyze_behavior(self._action_history[-10:])
            time.sleep(5)
            
    def on_tool_call(self, tool_name: str, params: Dict[str, Any]) -> SecurityDecision:
        """Checks a specific tool call against threat patterns."""
        # Record for behavioral analysis
        self._action_history.append({
            "tool": tool_name,
            "params": params,
            "timestamp": time.time()
        })
        
        if tool_name not in self.dangerous_tools:
            return SecurityDecision(True, "Tool is inherently safe", "LOW")
            
        # Specific checks
        if tool_name == "run_command":
            cmd = str(params.get("command", "")).lower()
            if "curl" in cmd and "-d" in cmd:
                # Potential data exfiltration via curl POST
                return SecurityDecision(False, "Potential data exfiltration detected", "HIGH")
                
        if tool_name in ["read_file", "write_file"]:
            path = str(params.get("path", ""))
            for pattern in self.suspicious_paths:
                if re.search(pattern, path):
                    return SecurityDecision(False, f"Access to sensitive path blocked: {path}", "HIGH")
                    
        return SecurityDecision(True, "No specific threat detected for parameters", "MEDIUM")
        
    def analyze_behavior(self, recent_actions: List[Dict[str, Any]]) -> ThreatAssessment:
        """Heuristic behavioral analysis."""
        # E.g. Check for rapid mass-deletion
        delete_count = sum(1 for a in recent_actions if a.get("tool") in ["run_command", "kill_process"] and "rm " in str(a.get("params", {})))
        
        if delete_count >= 3:
            threat = ThreatAssessment(True, "mass_deletion", 0.9, f"{delete_count} deletion commands in short sequence")
            self._threat_log.append({"timestamp": time.time(), "assessment": threat.__dict__})
            return threat
            
        return ThreatAssessment(False, "none", 0.0, "Behavior appears normal")
        
    def get_threat_log(self) -> List[Dict[str, Any]]:
        return self._threat_log
