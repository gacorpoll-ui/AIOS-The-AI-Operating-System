import platform
import subprocess
from typing import Dict, List, Any

def get_system_info() -> Dict[str, Any]:
    info = {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": platform.node()
    }
    try:
        import psutil
        info.update({
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "cpu_count": psutil.cpu_count(logical=True),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        })
        import time
        info["uptime_seconds"] = int(time.time() - psutil.boot_time())
    except ImportError:
        pass
    return info

def get_network_info() -> Dict[str, Any]:
    try:
        import psutil
        import socket
        
        interfaces = {}
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        
        for name, addrs in net_if_addrs.items():
            if_info = {
                "is_up": net_if_stats[name].isup if name in net_if_stats else False,
                "addresses": []
            }
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    if_info["addresses"].append({"type": "ipv4", "address": addr.address})
                elif addr.family == socket.AF_INET6:
                    if_info["addresses"].append({"type": "ipv6", "address": addr.address})
            interfaces[name] = if_info
        return {"interfaces": interfaces}
    except ImportError:
        return {"error": "psutil not installed"}

def get_installed_packages() -> List[str]:
    try:
        result = subprocess.run(["pip", "list", "--format=json"], timeout=30, capture_output=True, text=True, check=True)
        import json
        packages = json.loads(result.stdout)
        return [f"{pkg['name']}=={pkg['version']}" for pkg in packages]
    except Exception:
        try:
            result = subprocess.run(["pip", "freeze"], timeout=30, capture_output=True, text=True)
            return [line.strip() for line in result.stdout.split('\n') if line.strip()]
        except Exception as e:
            return [f"Error: {str(e)}"]

def read_logs(log_file: str, last_n_lines: int = 100) -> str:
    import os
    if not os.path.exists(log_file):
        raise FileNotFoundError(f"Log file not found: {log_file}")
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        if len(lines) > last_n_lines:
            lines = lines[-last_n_lines:]
        return "".join(lines)
    except Exception as e:
        raise RuntimeError(f"Failed to read log file: {str(e)}")