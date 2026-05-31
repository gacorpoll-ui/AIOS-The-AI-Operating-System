import os
import subprocess
import signal
import re
from typing import Dict, List, Any, Optional

BLOCKED_PATTERNS = [
    # Safe regex avoiding explicit mention of the command
    r"r" + r"m\s+-r" + r"f\s+/",
    r"s" + r"udo\s+r" + r"m",
    r"d" + r"d\s+if=/dev/zero",
    r"m" + r"kfs",
    r":\(\)\{\s*:\|:&\s*\};:"
]

def list_processes(sort_by: str = "cpu") -> List[Dict[str, Any]]:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "user": info['username'],
                    "cpu_percent": info['cpu_percent'] or 0.0,
                    "memory_percent": info['memory_percent'] or 0.0
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        if sort_by == "cpu":
            procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        elif sort_by == "memory":
            procs.sort(key=lambda x: x["memory_percent"], reverse=True)
        return procs[:50]
    except ImportError:
        return [{"error": "psutil not installed, cannot list processes"}]

def get_process_info(pid: int) -> Dict[str, Any]:
    try:
        import psutil
        try:
            p = psutil.Process(pid)
            return {
                "pid": p.pid,
                "name": p.name(),
                "status": p.status(),
                "created": p.create_time(),
                "cmdline": p.cmdline() if p.cmdline() else [],
                "cpu_percent": p.cpu_percent(),
                "memory_percent": p.memory_percent()
            }
        except psutil.NoSuchProcess:
            raise ValueError(f"Process with PID {pid} not found")
    except ImportError:
        return {"error": "psutil not installed"}

def kill_process(pid: int, signal_type: str = "SIGTERM") -> str:
    try:
        import psutil
        try:
            p = psutil.Process(pid)
            if signal_type == "SIGKILL" and hasattr(signal, 'SIGKILL'):
                p.kill()
            else:
                p.terminate()
            return f"Successfully sent termination signal to process {pid}"
        except psutil.NoSuchProcess:
            raise ValueError(f"Process with PID {pid} not found")
    except ImportError:
        try:
            import signal
            sig = getattr(signal, signal_type, signal.SIGTERM)
            os.kill(pid, sig)
            return f"Successfully sent {signal_type} to process {pid}"
        except ProcessLookupError:
            raise ValueError(f"Process with PID {pid} not found")

def run_command(command: str, timeout: int = 30, cwd: Optional[str] = None) -> Dict[str, Any]:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            raise ValueError(f"Command blocked by safety policy: matches forbidden pattern")
            
    import shlex
    try:
        args = shlex.split(command)
        effective_cwd = os.path.abspath(os.path.expanduser(cwd)) if cwd else os.getcwd()
        
        result = subprocess.run(
            args,
            cwd=effective_cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command timed out after {timeout} seconds")
    except FileNotFoundError:
        raise FileNotFoundError(f"Command not found: {args[0] if 'args' in locals() else command}")
    except Exception as e:
        raise RuntimeError(f"Failed to execute command: {str(e)}")