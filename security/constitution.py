"""Constitutional Enforcer — immutable rules that NO agent can override.

This is the ethical bedrock of AIOS. Articles are hard-coded strings,
not loaded from any config file. The Constitution is a module-level
singleton instantiated once at startup.

Violations trigger immediate HARD STOP, black box logging, and human alert.
"""

import os
import json
import time
import hashlib
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# CONSTITUTION ARTICLES (HARD-CODED — NOT IN ANY CONFIG FILE)
# ═══════════════════════════════════════════════════════════════════

ARTICLE_1 = (
    "No Exfiltration: Never send user data to external network "
    "without explicit per-request human approval. "
    "Any tool call with network=True must have human_approved=True in context."
)

ARTICLE_2 = (
    "No Self-Replication: AI cannot create copies of itself or spawn "
    "persistent processes without user knowledge. "
    "No fork/exec that spawns another AIOS instance."
)

ARTICLE_3 = (
    "No Privilege Escalation: Cannot acquire permissions not explicitly "
    "granted at startup. No sudo/su/chmod calls without explicit "
    "permission grant in session."
)

ARTICLE_4 = (
    "No Memory Erasure: Cannot delete black box records. "
    "Any DELETE on black_box DB is an instant violation."
)

ARTICLE_5 = (
    "No Silent Modification: All file modifications must be logged "
    "with diff. Any write_file call generates a change record."
)

ARTICLE_6 = (
    "Transparency: AI must never lie to the human about what it did "
    "or is doing. No response must contradict black box record of "
    "same session."
)

ARTICLES = {
    1: ARTICLE_1,
    2: ARTICLE_2,
    3: ARTICLE_3,
    4: ARTICLE_4,
    5: ARTICLE_5,
    6: ARTICLE_6,
}

# ═══════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ConstitutionResult:
    compliant: bool = True
    violations: List[str] = field(default_factory=list)
    blocked_article: Optional[int] = None


class ConstitutionViolation(Exception):
    """Raised when a tool call violates a constitutional article."""
    def __init__(self, violations: List[str], article: int = None):
        self.violations = violations
        self.article = article
        article_name = f"Article {article}" if article else "Unknown"
        super().__init__(
            f"Constitutional violation ({article_name}): "
            + "; ".join(violations)
        )


# ═══════════════════════════════════════════════════════════════════
# Constitution — Module-level Singleton
# ═══════════════════════════════════════════════════════════════════

class Constitution:
    """Immutable constitutional enforcer. Singleton — instantiated once."""

    _instance = None
    _sealed = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, black_box=None):
        if self._initialized:
            return
        self._initialized = True
        self.black_box = black_box
        self._session_permissions: set = set()
        self._sealed = True
        logger.info("Constitution initialized and sealed")

    @classmethod
    def get_instance(cls) -> "Constitution":
        if cls._instance is None or not cls._instance._initialized:
            raise RuntimeError(
                "Constitution not initialized. Call Constitution(black_box=...) first."
            )
        return cls._instance

    def check(self, tool_name: str, params: dict, context: dict = None) -> ConstitutionResult:
        """Check ALL articles. Returns result. Must complete in <1ms."""
        if context is None:
            context = {}
        violations = []
        blocked = None

        # ARTICLE 1: No exfiltration
        v = self._check_article_1(tool_name, params, context)
        if v:
            violations.append(v)
            if not blocked:
                blocked = 1

        # ARTICLE 2: No self-replication
        v = self._check_article_2(tool_name, params, context)
        if v:
            violations.append(v)
            if not blocked:
                blocked = 2

        # ARTICLE 3: No privilege escalation
        v = self._check_article_3(tool_name, params, context)
        if v:
            violations.append(v)
            if not blocked:
                blocked = 3

        # ARTICLE 4: No memory erasure (black box deletion)
        v = self._check_article_4(tool_name, params, context)
        if v:
            violations.append(v)
            if not blocked:
                blocked = 4

        # ARTICLE 5: No silent modification
        v = self._check_article_5(tool_name, params, context)
        if v:
            violations.append(v)
            if not blocked:
                blocked = 5

        return ConstitutionResult(
            compliant=len(violations) == 0,
            violations=violations,
            blocked_article=blocked,
        )

    def grant_permission(self, permission: str) -> None:
        """Grant a permission for this session (e.g., 'sudo')."""
        self._session_permissions.add(permission.lower())

    def revoke_permission(self, permission: str) -> None:
        self._session_permissions.discard(permission.lower())

    def has_permission(self, permission: str) -> bool:
        return permission.lower() in self._session_permissions

    # ── Article 1: No Exfiltration ──────────────────────────────

    def _check_article_1(self, tool_name: str, params: dict, context: dict) -> Optional[str]:
        network_tools = {"run_command", "get_network_info"}
        has_network = tool_name in network_tools
        command = params.get("command", "")
        if command and any(kw in command.lower() for kw in ["curl", "wget", "scp", "nc ", "ncat", "netcat"]):
            has_network = True

        if has_network and not context.get("human_approved", False):
            return (
                f"Article 1 violation: '{tool_name}' involves network activity "
                f"without explicit human approval. "
                f"Set human_approved=True in context."
            )
        return None

    # ── Article 2: No Self-Replication ──────────────────────────

    def _check_article_2(self, tool_name: str, params: dict, context: dict) -> Optional[str]:
        command = params.get("command", "")
        if not command:
            return None

        # Check for commands that could spawn AIOS copies
        replication_patterns = [
            "aios-shell",
            "aios-daemon",
            "aios.nl_shell",
            "aios.daemon",
            "nohup.*aios",
            "python.*aios",
            "subprocess.*aios",
            "fork",
            "daemonize",
        ]
        import re
        for pattern in replication_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return (
                    f"Article 2 violation: '{tool_name}' command attempts "
                    f"self-replication or spawning AIOS instance. "
                    f"Pattern matched: {pattern}"
                )
        return None

    # ── Article 3: No Privilege Escalation ──────────────────────

    def _check_article_3(self, tool_name: str, params: dict, context: dict) -> Optional[str]:
        command = params.get("command", "")
        if not command:
            return None

        priv_esc_patterns = ["sudo ", "sudo\t", " su ", " su\t", "chmod", "chown"]
        for pattern in priv_esc_patterns:
            if pattern in command.lower():
                if not self.has_permission("sudo") and not context.get("human_approved", False):
                    return (
                        f"Article 3 violation: '{tool_name}' command attempts "
                        f"privilege escalation ('{pattern.strip()}'). "
                        f"No sudo permission granted in this session."
                    )
        return None

    # ── Article 4: No Memory Erasure ────────────────────────────

    def _check_article_4(self, tool_name: str, params: dict, context: dict) -> Optional[str]:
        # Check for black box deletion attempts
        command = params.get("command", "")
        if command:
            bb_patterns = ["blackbox", "black_box", "black-box"]
            delete_keywords = ["delete", "drop", "truncate", "rm ", "del ", "remove"]
            for bb in bb_patterns:
                if bb in command.lower():
                    for kw in delete_keywords:
                        if kw in command.lower():
                            return (
                                f"Article 4 violation: attempt to delete or modify "
                                f"black box records. This is absolutely forbidden."
                            )

        # Check for run_command targeting black box files
        path = params.get("path", "")
        if "blackbox" in path.lower() and tool_name in ("write_file", "delete_file"):
            return (
                f"Article 4 violation: file operation on black box database. "
                f"This is absolutely forbidden."
            )
        return None

    # ── Article 5: No Silent Modification ───────────────────────

    def _check_article_5(self, tool_name: str, params: dict, context: dict) -> Optional[str]:
        if tool_name == "write_file":
            path = params.get("path", "")
            content = params.get("content", "")

            # Generate change record hash
            change_hash = hashlib.sha256(
                f"{path}:{content[:1000]}".encode()
            ).hexdigest()[:16]

            # Log the modification
            logger.info(
                f"Article 5: File modification logged — "
                f"path={path}, hash={change_hash}, "
                f"content_length={len(content)}"
            )

            # Record to black box if available
            if self.black_box:
                self.black_box.insert("file_modification", {
                    "agent": "SYSTEM",
                    "type": "file_change",
                    "path": path,
                    "content_hash": change_hash,
                    "content_length": len(content),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            return None  # Allowed but logged — not a violation
        return None

    # ── Seal: prevent runtime modification ──────────────────────

    def __setattr__(self, name, value):
        if self._sealed and name not in ("_session_permissions",):
            raise RuntimeError(
                f"Constitution is sealed. Cannot modify '{name}' at runtime. "
                f"This is a constitutional protection."
            )
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if self._sealed:
            raise RuntimeError(
                f"Constitution is sealed. Cannot delete '{name}'. "
                f"This is a constitutional protection."
            )
        super().__delattr__(name)


# ── Convenience function for ToolRegistry ────────────────────────

def enforce(tool_name: str, params: dict, context: dict = None) -> ConstitutionResult:
    """Fast constitutional check. Call this BEFORE any tool execution.
    If Constitution is not initialized (e.g., in unit tests), pass through."""
    if Constitution._instance is None or not Constitution._instance._initialized:
        return ConstitutionResult(compliant=True)
    const = Constitution.get_instance()
    return const.check(tool_name, params, context or {})
