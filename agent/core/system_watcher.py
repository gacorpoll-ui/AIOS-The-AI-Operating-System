import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class SystemState:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    active_connections: int
    running_processes: int

@dataclass
class Anomaly:
    type: str
    severity: str
    description: str

@dataclass
class Prediction:
    predicted_cpu: float
    predicted_memory: float
    reasoning: str

class SystemWatcher:
    """Monitors system state continuously."""
    
    def __init__(self):
        self.history: List[SystemState] = []
        
    def get_current_state(self) -> SystemState:
        """Collects current system metrics."""
        try:
            import psutil
            state = SystemState(
                timestamp=time.time(),
                cpu_percent=psutil.cpu_percent(interval=0.1),
                memory_percent=psutil.virtual_memory().percent,
                disk_percent=psutil.disk_usage('/').percent,
                active_connections=len(psutil.net_connections()),
                running_processes=len(psutil.pids())
            )
        except ImportError:
            # Fallback for environments without psutil
            state = SystemState(
                timestamp=time.time(),
                cpu_percent=0.0,
                memory_percent=0.0,
                disk_percent=0.0,
                active_connections=0,
                running_processes=0
            )
            
        self.history.append(state)
        # Keep last 2 hours of history (assuming 30s polling = 240 samples)
        if len(self.history) > 240:
            self.history.pop(0)
            
        return state
        
    def detect_anomaly(self, state: SystemState) -> List[Anomaly]:
        """Simple heuristic anomaly detection."""
        anomalies = []
        
        if state.cpu_percent > 90.0:
            # Check if it's sustained (last 4 samples = 2 mins)
            if len(self.history) >= 4 and all(s.cpu_percent > 90.0 for s in self.history[-4:]):
                anomalies.append(Anomaly("High CPU", "HIGH", f"CPU has been at >90% for sustained period (current: {state.cpu_percent}%)"))
                
        if state.disk_percent > 95.0:
            anomalies.append(Anomaly("Low Disk", "CRITICAL", f"Disk is {state.disk_percent}% full. Risk of system crash."))
            
        if state.memory_percent > 90.0:
            anomalies.append(Anomaly("High Memory", "HIGH", f"Memory usage at {state.memory_percent}%."))
            
        return anomalies
        
    def predict_resource_needs(self) -> Prediction:
        """Simple heuristic prediction based on trend."""
        if len(self.history) < 10:
            return Prediction(50.0, 50.0, "Insufficient data for prediction")
            
        recent = self.history[-10:]
        avg_cpu = sum(s.cpu_percent for s in recent) / len(recent)
        avg_mem = sum(s.memory_percent for s in recent) / len(recent)
        
        # Trend (last 3 vs previous 7)
        recent_3_cpu = sum(s.cpu_percent for s in recent[-3:]) / 3
        older_7_cpu = sum(s.cpu_percent for s in recent[:7]) / 7
        
        trend = recent_3_cpu - older_7_cpu
        predicted_cpu = max(0.0, min(100.0, avg_cpu + trend))
        
        return Prediction(
            predicted_cpu=predicted_cpu,
            predicted_memory=avg_mem,
            reasoning=f"Based on recent average with a trend of {trend:+.1f}%"
        )
