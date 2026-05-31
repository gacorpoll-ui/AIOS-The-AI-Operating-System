"""Parliament System — Multi-agent deliberation for high-stakes decisions.

When a high-stakes tool is about to execute with low confidence, the parliament
convenes: multiple agents deliberate and the judge renders a FINAL verdict.
"""

import os
import json
import time
import sqlite3
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── YAML Parser ────────────────────────────────────────────────────

def _parse_yaml(path: str) -> Dict[str, Any]:
    """Minimal YAML parser supporting: scalars, lists, dicts, nesting."""
    with open(path, "r") as f:
        lines = f.readlines()
    return _parse_lines(lines, 0, 0)[0]


def _parse_lines(lines, start, min_indent):
    result = {}
    i = start
    current_key = None
    current_list = None

    while i < len(lines):
        raw = lines[i]
        stripped = raw.rstrip()
        line = stripped.lstrip()

        if not line or line.startswith("#"):
            i += 1
            continue

        indent = len(stripped) - len(line)
        if indent < min_indent:
            break

        # List item
        if line.startswith("- "):
            item_content = line[2:].strip()
            if current_list is not None:
                if ":" in item_content:
                    # Dict item in list
                    d = {}
                    k, _, v = item_content.partition(":")
                    d[k.strip()] = _yaml_val(v)
                    # Check for more keys at deeper indent
                    j = i + 1
                    item_indent = indent + 2
                    while j < len(lines):
                        jr = lines[j].rstrip()
                        jl = jr.lstrip()
                        if not jl or jl.startswith("#"):
                            j += 1
                            continue
                        ji = len(jr) - len(jl)
                        if ji < item_indent:
                            break
                        if ":" in jl and not jl.startswith("- "):
                            k2, _, v2 = jl.partition(":")
                            d[k2.strip()] = _yaml_val(v2)
                        j += 1
                    current_list.append(d)
                    i = j
                    continue
                else:
                    current_list.append(_yaml_val(item_content))
            i += 1
            continue

        # Key: value or Key:
        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()

            if not rest:
                # Check if next non-empty line is a list or dict
                j = i + 1
                while j < len(lines):
                    nr = lines[j].rstrip()
                    nl = nr.lstrip()
                    if nl and not nl.startswith("#"):
                        break
                    j += 1

                if j < len(lines) and lines[j].lstrip().startswith("- "):
                    current_list = []
                    result[key] = current_list
                    current_key = key
                else:
                    sub_dict, new_i = _parse_lines(lines, j, indent + 2)
                    result[key] = sub_dict
                    i = new_i
                    current_list = None
                    continue
            else:
                result[key] = _yaml_val(rest)
                current_list = None

        i += 1

    return result, i


def _yaml_val(s: str) -> Any:
    s = s.strip()
    if s.startswith("#"):
        return None
    ci = s.find(" #")
    if ci > 0:
        s = s[:ci].strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s.strip('"').strip("'")


# ── Dataclasses ─────────────────────────────────────────────────────

@dataclass
class AgentArgument:
    agent_id: str
    role: str
    position: str        # "for" | "against" | "neutral" | "verdict"
    reasoning: str
    confidence: float    # 0.0-1.0
    round_num: int
    timestamp: str = ""

@dataclass
class ParliamentVerdict:
    verdict: str         # APPROVE / APPROVE_WITH_CONDITIONS / REJECT / DEFER
    reasoning: str
    confidence: float
    total_rounds: int
    total_time_ms: int
    arguments: List[AgentArgument]
    decision: str        # the original decision being deliberated

@dataclass
class ParliamentRecord:
    id: Optional[int] = None
    timestamp: str = ""
    decision: str = ""
    tool_name: str = ""
    tool_params: str = ""
    verdict: str = ""
    verdict_reasoning: str = ""
    total_rounds: int = 0
    total_time_ms: int = 0
    arguments_json: str = ""  # Full JSON of all arguments


# ── Parliament ─────────────────────────────────────────────────────

class Parliament:
    """Multi-agent deliberation for high-stakes decisions."""

    def __init__(self, config_path: str = None, black_box=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "parliament.yaml")

        self.config = _parse_yaml(config_path) if os.path.exists(config_path) else {}
        self.high_stakes_tools = self.config.get("high_stakes_tools", [])
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.50))

        p_cfg = self.config.get("parliament", {})
        self.max_rounds = int(p_cfg.get("max_rounds", 3))
        self.max_time_seconds = int(p_cfg.get("max_time_seconds", 90))
        self.timeout_per_round = int(p_cfg.get("timeout_per_round", 25))
        self.agents = p_cfg.get("agents", [])
        self.black_box = black_box  # Optional BlackBoxRecorder reference

        # Internal argument log
        self._argument_log: List[AgentArgument] = []

    def should_convene(self, tool_name: str, confidence: float) -> bool:
        """Return True if parliament should be convened for this decision."""
        return (
            tool_name in self.high_stakes_tools
            and confidence < self.confidence_threshold
        )

    def convene(self, decision: str, tool_name: str,
                tool_params: Dict[str, Any] = None,
                context: str = "") -> ParliamentVerdict:
        """Convene parliament. Returns FINAL verdict. Logged to black box."""
        start = time.time()
        self._argument_log = []

        if tool_params is None:
            tool_params = {}

        params_str = json.dumps(tool_params)

        logger.info(f"Parliament convened for: {decision}")

        for round_num in range(1, self.max_rounds + 1):
            elapsed = time.time() - start
            if elapsed > self.max_time_seconds:
                logger.warning(f"Parliament timed out after {elapsed:.1f}s")
                break

            for agent_cfg in self.agents:
                agent_id = agent_cfg.get("id", "unknown")
                role = agent_cfg.get("role", "")

                argument = self._generate_argument(
                    agent_id=agent_id,
                    role=role,
                    decision=decision,
                    tool_name=tool_name,
                    tool_params=params_str,
                    context=context,
                    round_num=round_num,
                )
                self._argument_log.append(argument)

                # Judge renders verdict in final round
                if agent_id == "judge" and round_num == self.max_rounds:
                    verdict = self._render_verdict(
                        decision=decision,
                        tool_name=tool_name,
                        tool_params=params_str,
                        total_time_ms=int((time.time() - start) * 1000),
                    )
                    self._log_to_black_box(verdict, tool_name, params_str)
                    return verdict

        # Fallback if we didn't reach judge in final round
        verdict = self._render_verdict(
            decision=decision,
            tool_name=tool_name,
            tool_params=params_str,
            total_time_ms=int((time.time() - start) * 1000),
        )
        self._log_to_black_box(verdict, tool_name, params_str)
        return verdict

    def _generate_argument(self, agent_id: str, role: str,
                           decision: str, tool_name: str,
                           tool_params: str, context: str,
                           round_num: int) -> AgentArgument:
        """Generate an agent's argument (simulated deliberation)."""
        ts = datetime.now(timezone.utc).isoformat()

        if agent_id == "advocate":
            position = "for"
            reasoning = (
                f"The action '{decision}' using tool '{tool_name}' should proceed. "
                f"The user's intent appears clear and the tool is designed for this purpose."
            )
            confidence = 0.75

        elif agent_id == "critic":
            position = "against"
            reasoning = (
                f"Caution: '{tool_name}' is a high-stakes tool. "
                f"The action '{decision}' could have unintended consequences. "
                f"Consider if there are safer alternatives or if user confirmation is needed."
            )
            confidence = 0.70

        elif agent_id == "risk_assessor":
            position = "neutral"
            reasoning = (
                f"Risk analysis for '{decision}': "
                f"Tool '{tool_name}' with params {tool_params}. "
                f"Potential damage is {'high' if tool_name in ('kill_process', 'write_file') else 'moderate'}. "
                f"Recovery options: rollback from memory, check black box history."
            )
            confidence = 0.65

        elif agent_id == "judge":
            position = "verdict"
            # Judge reviews all previous arguments
            for_count = sum(1 for a in self._argument_log if a.position == "for")
            against_count = sum(1 for a in self._argument_log if a.position == "against")
            risk_count = sum(1 for a in self._argument_log if a.position == "neutral")

            if against_count > for_count:
                reasoning = (
                    f"After {round_num} rounds of deliberation, the opposition outweighs support "
                    f"({against_count} against vs {for_count} for). "
                    f"Risk factors identified: {risk_count}. "
                    f"Verdict: REJECT — action requires additional user confirmation."
                )
                confidence = 0.60
            elif for_count > against_count:
                reasoning = (
                    f"After {round_num} rounds of deliberation, support outweighs opposition "
                    f"({for_count} for vs {against_count} against). "
                    f"Risk factors acknowledged but manageable. "
                    f"Verdict: APPROVE_WITH_CONDITIONS — proceed with user confirmation."
                )
                confidence = 0.80
            else:
                reasoning = (
                    f"After {round_num} rounds, arguments are balanced. "
                    f"Verdict: DEFER — requires explicit user review before proceeding."
                )
                confidence = 0.50
        else:
            position = "neutral"
            reasoning = f"Agent {agent_id} has no specific input."
            confidence = 0.50

        argument = AgentArgument(
            agent_id=agent_id,
            role=role,
            position=position,
            reasoning=reasoning,
            confidence=confidence,
            round_num=round_num,
            timestamp=ts,
        )

        logger.info(f"Parliament [{agent_id}]: {position} (confidence={confidence:.0%})")
        return argument

    def _render_verdict(self, decision: str, tool_name: str,
                        tool_params: str, total_time_ms: int) -> ParliamentVerdict:
        """Find the judge's argument and render verdict."""
        judge_args = [a for a in self._argument_log
                      if a.agent_id == "judge" and a.position == "verdict"]

        if judge_args:
            last_judge = judge_args[-1]
            # Parse verdict from reasoning text
            if "REJECT" in last_judge.reasoning:
                verdict = "REJECT"
            elif "APPROVE_WITH_CONDITIONS" in last_judge.reasoning:
                verdict = "APPROVE_WITH_CONDITIONS"
            elif "DEFER" in last_judge.reasoning:
                verdict = "DEFER"
            else:
                verdict = "APPROVE"

            return ParliamentVerdict(
                verdict=verdict,
                reasoning=last_judge.reasoning,
                confidence=last_judge.confidence,
                total_rounds=max(a.round_num for a in self._argument_log),
                total_time_ms=total_time_ms,
                arguments=self._argument_log.copy(),
                decision=decision,
            )

        # No judge found — default
        return ParliamentVerdict(
            verdict="DEFER",
            reasoning="No judge argument found. Defaulting to DEFER.",
            confidence=0.0,
            total_rounds=0,
            total_time_ms=total_time_ms,
            arguments=self._argument_log.copy(),
            decision=decision,
        )

    def _log_to_black_box(self, verdict: ParliamentVerdict,
                          tool_name: str, tool_params: str) -> None:
        """Permanently store parliament record in black box."""
        if not self.black_box:
            logger.warning("No black box available — parliament record not stored")
            return

        args_json = json.dumps([
            {
                "agent_id": a.agent_id,
                "role": a.role,
                "position": a.position,
                "reasoning": a.reasoning,
                "confidence": a.confidence,
                "round": a.round_num,
                "timestamp": a.timestamp,
            }
            for a in verdict.arguments
        ])

        record = ParliamentRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=verdict.decision,
            tool_name=tool_name,
            tool_params=tool_params,
            verdict=verdict.verdict,
            verdict_reasoning=verdict.reasoning,
            total_rounds=verdict.total_rounds,
            total_time_ms=verdict.total_time_ms,
            arguments_json=args_json,
        )

        try:
            conn = self.black_box._conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parliament_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    decision TEXT,
                    tool_name TEXT,
                    tool_params TEXT,
                    verdict TEXT,
                    verdict_reasoning TEXT,
                    total_rounds INTEGER,
                    total_time_ms INTEGER,
                    arguments_json TEXT
                )
            """)
            conn.execute("""
                INSERT INTO parliament_records
                (timestamp, decision, tool_name, tool_params, verdict,
                 verdict_reasoning, total_rounds, total_time_ms, arguments_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (record.timestamp, record.decision, record.tool_name,
                  record.tool_params, record.verdict, record.verdict_reasoning,
                  record.total_rounds, record.total_time_ms, record.arguments_json))
            conn.commit()
            logger.info(f"Parliament record stored in black box: verdict={verdict.verdict}")
        except Exception as e:
            logger.error(f"Failed to store parliament record: {e}")

    def get_parliament_history(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent parliament verdicts from black box."""
        if not self.black_box:
            return []
        try:
            conn = self.black_box._conn()
            cursor = conn.execute("""
                SELECT id, timestamp, decision, tool_name, verdict,
                       total_rounds, total_time_ms
                FROM parliament_records
                ORDER BY id DESC LIMIT ?
            """, (n,))
            return [dict(zip([c[0] for c in cursor.description], row)) for row in cursor]
        except Exception:
            return []
