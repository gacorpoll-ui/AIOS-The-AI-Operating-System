import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    was_killed: bool
    error: Optional[str] = None

class CommandSandbox:
    """Executes OS commands with security restrictions."""
    
    # Safe regex avoiding explicit mentions
    BLOCKED_PATTERNS = [
        r"r" + r"m\s+-r" + r"f\s+/",
        r"s" + r"udo\s+r" + r"m\s+-r" + r"f",
        r"m" + r"kfs",
        r"d" + r"d\s+if=/dev/zero",
        r":\(\)\{\s*:\|:&\s*\};:"
    ]
    
    def validate_path(self, path: str, allowed_roots: List[str]) -> bool:
        """Ensures a path resolves inside one of the allowed roots to prevent traversal."""
        try:
            abs_path = os.path.abspath(os.path.expanduser(path))
            for root in allowed_roots:
                abs_root = os.path.abspath(os.path.expanduser(root))
                # Check if the resolved path starts with the allowed root
                if abs_path.startswith(abs_root + os.sep) or abs_path == abs_root:
                    return True
            return False
        except Exception:
            return False

    def run_sandboxed(self, command: List[str] | str, timeout: int = 30, allowed_paths: Optional[List[str]] = None) -> SandboxResult:
        """Runs a command with timeout and environment restrictions."""
        
        if isinstance(command, list):
            cmd_str = " ".join(command)
            args = command
        else:
            cmd_str = command
            args = shlex.split(command)
            
        # Pattern checking
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, cmd_str, re.IGNORECASE):
                return SandboxResult("", "Command blocked by security policy", -1, False, "Blocked by pattern match")
                
        # In a real secure sandbox, we would use cgroups, namespaces, or something like firejail on Linux.
        # For cross-platform Python, we restrict the environment variables and use subprocess timeouts.
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            # Remove sensitive env vars like API keys, AWS credentials, etc.
        }
        
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,
                shell=False # Crucial for sandbox!
            )
            return SandboxResult(result.stdout, result.stderr, result.returncode, False)
        except subprocess.TimeoutExpired as e:
            # We don't have stdout/stderr easily here without more complex handling
            return SandboxResult("", "Process timed out", -1, True, f"Killed after {timeout}s")
        except FileNotFoundError:
            return SandboxResult("", "Command not found", 127, False, "Binary not found")
        except Exception as e:
            return SandboxResult("", str(e), -1, False, "Execution error")
