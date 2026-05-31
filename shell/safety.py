import re
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class SafetyResult:
    allowed: bool
    reason: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

class SafetyChecker:
    """Evaluates intent and planned tools for dangerous operations."""
    
    # Patterns that are absolutely forbidden
    FORBIDDEN_PATTERNS = [
        r"(?i)\bformat\b.*\b(c:|/dev/sd|/dev/nvme)\b",
        r"(?i)format\s+C:",
        r"(?i)rm\s+-rf\s+/",
        r"(?i)rm\s+-rf\s+~",
        r"(?i)wipe\s+disk"
    ]
    
    # Actions that require user confirmation
    DANGEROUS_ACTIONS = [
        r"(?i)\bsudo\b",
        r"(?i)\bdelete\b.*\b(all|everything)\b",
        r"(?i)\bkill\b.*\b(all|-9)\b",
        r"(?i)chmod\s+-R\s+777",
        r"(?i)chown\s+-R"
    ]
    
    def __init__(self):
        pass
        
    def check_intent(self, user_input: str, planned_tools: List[Dict[str, Any]]) -> SafetyResult:
        """Detects if intent is dangerous."""
        
        # 1. Check raw input against forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, user_input):
                return SafetyResult(
                    allowed=False, 
                    reason=f"Action blocked: matches forbidden pattern.",
                    risk_level="HIGH"
                )
                
        # 2. Check planned tool executions
        has_destructive_tools = False
        requires_sudo = False
        
        for call in planned_tools:
            tool_name = call.get("tool", "")
            params = call.get("params", {})
            
            # Identify destructive tools
            if tool_name in ["run_command", "kill_process", "write_file", "delete_all"]:
                cmd = str(params.get("command", "")).lower()
                
                # Check command contents for forbidden patterns
                for pattern in self.FORBIDDEN_PATTERNS:
                    if re.search(pattern, cmd):
                        return SafetyResult(
                            allowed=False, 
                            reason=f"Command '{cmd}' is strictly forbidden.",
                            risk_level="HIGH"
                        )
                
                # Check for medium-risk patterns requiring confirmation
                if tool_name == "run_command":
                    has_destructive_tools = True
                    if "sudo " in cmd:
                        requires_sudo = True
                        
        if requires_sudo:
            return SafetyResult(
                allowed=True,
                reason="Command uses elevated privileges (sudo).",
                risk_level="HIGH"
            )
            
        if has_destructive_tools:
            return SafetyResult(
                allowed=True,
                reason="Execution involves modifying system state.",
                risk_level="MEDIUM"
            )
            
        return SafetyResult(
            allowed=True,
            reason="Action appears safe.",
            risk_level="LOW"
        )
        
    def require_confirmation(self, action_description: str) -> bool:
        """Presents clear confirmation prompt.
        Note: In the actual shell loop, we use display.print_confirmation_prompt instead,
        this method is mainly here for compatibility with the spec.
        """
        from .display import print_confirmation_prompt
        return print_confirmation_prompt(action_description)
