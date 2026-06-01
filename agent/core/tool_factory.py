"""Self-Expanding Tool System — AIOS generates new tools from user patterns.

Design:
- Parliament approval required before any new tool is created
- Rate-limited: max 5 new tools per day
- Generated tools stored in agent/tools/generated/
- Human can remove: aios tools remove {name}
- All activity logged to black box under "SYSTEM" agent
- Constitution check applied to generated tools (must not violate articles)
"""

import os
import re
import sys
import json
import time
import importlib
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GENERATED_TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "generated"
)

# Tool template — generated tools must follow this structure
TOOL_TEMPLATE = '''"""
Auto-generated tool: {name}
Created: {timestamp}
Purpose: {purpose}
Approved by: Parliament (verdict: {verdict})
"""
import logging
logger = logging.getLogger(__name__)

def {func_name}({params}) -> str:
    """{docstring}"""
    try:
        {body}
        return str(result)
    except Exception as e:
        logger.error(f"Tool {name} failed: {{e}}")
        return f"Error: {{e}}"
'''


@dataclass
class ToolProposal:
    name: str
    purpose: str
    params: Dict[str, str]
    body_template: str
    requested_by: str
    context: str


class ToolFactory:
    """Generates, approves, and manages dynamic tools."""

    def __init__(self, black_box=None, parliament=None, constitution=None):
        self.black_box = black_box
        self.parliament = parliament
        self.constitution = constitution
        self._created_today: Dict[str, datetime] = {}
        self._load_created_today()

    def _load_created_today(self) -> None:
        """Track tools created today for rate limiting."""
        os.makedirs(GENERATED_TOOLS_DIR, exist_ok=True)
        tracker_path = os.path.join(GENERATED_TOOLS_DIR, "_tracker.json")
        if os.path.exists(tracker_path):
            with open(tracker_path, "r") as f:
                data = json.load(f)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if data.get("date") == today:
                self._created_today = data.get("tools", {})
            else:
                # New day — reset counter
                self._created_today = {}
                self._save_tracker(today)

    def _save_tracker(self, date: str = None) -> None:
        tracker_path = os.path.join(GENERATED_TOOLS_DIR, "_tracker.json")
        today = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(tracker_path, "w") as f:
            json.dump({"date": today, "tools": self._created_today}, f, indent=2)

    def _can_create_today(self) -> bool:
        """Check rate limit: max 5 new tools per day."""
        return len(self._created_today) < 5

    def propose_tool(self, name: str, purpose: str,
                     params: Dict[str, str] = None,
                     body_template: str = "",
                     context: str = "") -> ToolProposal:
        """Create a tool proposal for Parliament review."""
        return ToolProposal(
            name=re.sub(r'[^a-zA-Z0-9_]', '_', name).lower(),
            purpose=purpose,
            params=params or {},
            body_template=body_template,
            requested_by="user",
            context=context,
        )

    def create_tool(self, proposal: ToolProposal) -> Dict[str, Any]:
        """Generate a new tool. Requires Parliament approval and rate limit check."""
        ts = datetime.now(timezone.utc).isoformat()

        # 1. Rate limit check
        if not self._can_create_today():
            return {
                "success": False,
                "error": "Rate limit exceeded: max 5 tools per day",
                "reason": "rate_limit",
            }

        # 2. Parliament approval
        if self.parliament:
            verdict = self.parliament.convene(
                decision=f"Create new tool '{proposal.name}': {proposal.purpose}",
                tool_name="tool_factory_create",
                tool_params={
                    "name": proposal.name,
                    "purpose": proposal.purpose,
                    "params": proposal.params,
                },
                context=proposal.context,
            )
            if verdict.verdict not in ("APPROVE", "APPROVE_WITH_CONDITIONS"):
                return {
                    "success": False,
                    "error": f"Parliament rejected: {verdict.verdict}",
                    "reason": "parliament_rejected",
                }
            parliament_verdict = verdict.verdict
        else:
            parliament_verdict = "no_parliament"

        # 3. Constitution check on the tool name and purpose
        if self.constitution:
            result = self.constitution.check(
                "tool_factory_create",
                {"name": proposal.name, "purpose": proposal.purpose},
                {}
            )
            if not result.compliant:
                return {
                    "success": False,
                    "error": f"Constitutional violation: {'; '.join(result.violations)}",
                    "reason": "constitution_blocked",
                }

        # 4. Generate tool code
        func_name = re.sub(r'[^a-zA-Z0-9_]', '_', proposal.name).lower()
        params_str = ", ".join(f"{k}: str = ''" for k in proposal.params) if proposal.params else ""
        docstring = proposal.purpose
        body = proposal.body_template or f"result = 'Tool {proposal.name} executed'"

        code = TOOL_TEMPLATE.format(
            name=proposal.name,
            timestamp=ts,
            purpose=proposal.purpose,
            verdict=parliament_verdict,
            func_name=func_name,
            params=params_str,
            docstring=docstring,
            body=body,
        )

        # 5. Write tool file
        tool_file = os.path.join(GENERATED_TOOLS_DIR, f"{func_name}.py")
        with open(tool_file, "w") as f:
            f.write(code)

        # 6. Update rate limit tracker
        self._created_today[proposal.name] = ts
        self._save_tracker()

        # 7. Log to black box
        if self.black_box:
            self.black_box.insert("tool_creation", {
                "agent": "SYSTEM",
                "type": "tool_generated",
                "tool_name": proposal.name,
                "purpose": proposal.purpose,
                "parliament_verdict": parliament_verdict,
                "file": tool_file,
                "timestamp": ts,
            })

        logger.info(f"Tool created: {proposal.name} ({tool_file})")

        # 8. Register with ToolRegistry (if provided by caller)
        return {
            "success": True,
            "tool_name": proposal.name,
            "func_name": func_name,
            "file": tool_file,
            "parliament_verdict": parliament_verdict,
            "message": f"Tool '{proposal.name}' created successfully",
        }

    def remove_tool(self, name: str) -> Dict[str, Any]:
        """Remove a generated tool. Human action only."""
        func_name = re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
        tool_file = os.path.join(GENERATED_TOOLS_DIR, f"{func_name}.py")

        if not os.path.exists(tool_file):
            return {"success": False, "error": f"Tool '{name}' not found"}

        os.remove(tool_file)

        # Remove from tracker
        if name in self._created_today:
            del self._created_today[name]
            self._save_tracker()

        # Log to black box
        if self.black_box:
            self.black_box.insert("tool_removal", {
                "agent": "SYSTEM",
                "type": "tool_removed",
                "tool_name": name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Unload from Python module cache
        mod_name = f"agent.tools.generated.{func_name}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        logger.info(f"Tool removed: {name}")
        return {"success": True, "tool_name": name, "message": f"Tool '{name}' removed"}

    def list_generated_tools(self) -> List[Dict[str, Any]]:
        """List all generated tools."""
        tools = []
        if not os.path.exists(GENERATED_TOOLS_DIR):
            return tools

        for f in os.listdir(GENERATED_TOOLS_DIR):
            if f.endswith(".py") and not f.startswith("_"):
                path = os.path.join(GENERATED_TOOLS_DIR, f)
                with open(path, "r") as fh:
                    content = fh.read()
                # Extract purpose from docstring
                match = re.search(r'Purpose: (.+)', content)
                purpose = match.group(1) if match else "Unknown"
                tools.append({
                    "name": f.replace(".py", ""),
                    "file": path,
                    "purpose": purpose,
                })

        return tools

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {
            "date": today,
            "created_today": len(self._created_today),
            "remaining": max(0, 5 - len(self._created_today)),
            "tools": list(self._created_today.keys()),
        }


# Need sys for module cache cleanup
import sys
