import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from agent.models.llm_interface import LocalLLM
from agent.core.tool_registry import ToolRegistry, ConfirmationRequired
from agent.core.memory import MemoryEngine
from .display import print_response, print_error, print_tool_call, print_confirmation_prompt, ThinkSpinner
from .history import ShellHistory
from .safety import SafetyChecker, SafetyResult

logger = logging.getLogger(__name__)

@dataclass
class ShellResponse:
    message: str
    tool_calls: List[Dict[str, Any]]
    success: bool
    follow_up_suggestions: List[str]

class NLShell:
    
    def __init__(self, llm: LocalLLM, tools: ToolRegistry, memory: MemoryEngine):
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self.history = ShellHistory()
        self.safety = SafetyChecker()
        self._running = False
        self.voice_mode = False
        
    def run(self) -> None:
        self._running = True
        
        print("\nWelcome to AIOS NL Shell.")
        print("Type 'exit' or press Ctrl+D to quit.\n")
        
        while self._running:
            try:
                prefix = "ðŸŽ™ï¸  aios â¯ " if self.voice_mode else "aios â¯ "
                user_input = input(prefix).strip()
                
                if not user_input: continue
                if user_input.lower() in ["exit", "quit"]: break
                    
                if user_input.lower() == "--voice":
                    self.voice_mode = not self.voice_mode
                    print(f"Voice mode {'enabled' if self.voice_mode else 'disabled'}")
                    continue
                    
                response = self.interpret(user_input)
                print_response(response)
                
                # Voice feedback if enabled
                if self.voice_mode and response.message:
                    self.voice.speak(response.message, speed=1.0)
                
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            except Exception as e:
                print_error(f"Unexpected error: {str(e)}")
                
        print("\nShutting down AIOS shell. Goodbye.")
        
    def interpret(self, user_input: str) -> ShellResponse:
        if not self.llm.is_loaded:
            return ShellResponse(
                message="Error: Local LLM is not loaded. Please initialize the AI daemon first.",
                tool_calls=[], success=False, follow_up_suggestions=["Start daemon"]
            )
            
        with ThinkSpinner("Interpreting intent..."):
            schema = {
                "intent": "string",
                "tool_calls": [{"tool": "string", "params": "object"}],
                "requires_clarification": "boolean",
                "clarification_message": "string"
            }
            
            tool_specs = self.tools.list_tools()
            prompt = f"User input: {user_input}\nAvailable tools: {json.dumps(tool_specs)}"
            
            try:
                intent_plan = self.llm.generate_structured(prompt, schema)
            except Exception as e:
                return ShellResponse(message=f"Failed to interpret intent: {str(e)}", tool_calls=[], success=False, follow_up_suggestions=[])
                
        if intent_plan.get("requires_clarification", False) and intent_plan.get("clarification_message"):
            return ShellResponse(message=intent_plan["clarification_message"], tool_calls=[], success=True, follow_up_suggestions=[])
            
        tool_calls = intent_plan.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            tool_calls = []
            
        safety_result = self.safety.check_intent(user_input, tool_calls)
        if not safety_result.allowed:
            return ShellResponse(
                message=f"Operation blocked by security policy: {safety_result.reason}",
                tool_calls=[], success=False, follow_up_suggestions=[]
            )
            
        results = []; executed_tools = []; success = True
        
        for call in tool_calls:
            tool_name = call.get("tool")
            params = call.get("params", {})
            if not tool_name: continue
                
            tool_obj = self.tools.get_tool(tool_name)
            if not tool_obj:
                results.append(f"Tool {tool_name} not found")
                success = False
                continue
                
            print_tool_call(tool_name, params)
            
            confirmed = False
            if tool_obj.requires_confirmation or safety_result.risk_level in ["MEDIUM", "HIGH"]:
                action_desc = f"execute {tool_name} with params {params}"
                if safety_result.risk_level == "HIGH":
                    action_desc += f"\nRisk: {safety_result.reason}"
                confirmed = print_confirmation_prompt(action_desc)
                if not confirmed:
                    results.append(f"Execution of {tool_name} cancelled by user.")
                    success = False
                    break
            else:
                confirmed = True
                
            with ThinkSpinner(f"Running {tool_name}..."):
                try:
                    tool_result = self.tools.execute(tool_name, params, confirmed)
                    results.append(f"Tool {tool_name} returned: {tool_result.output}")
                    if not tool_result.success:
                        success = False
                        if tool_result.error:
                            results.append(f"Error: {tool_result.error}")
                            break
                    executed_tools.append(call)
                except Exception as e:
                    results.append(f"Tool execution failed: {str(e)}")
                    success = False
                    break
                    
        if not tool_calls:
            final_message = intent_plan.get("intent", "I didn't understand that request.")
        else:
            with ThinkSpinner("Summarizing results..."):
                summary_prompt = f"User asked: {user_input}\nTools executed and results:\n{json.dumps(results)}\nProvide a helpful human-readable response based ONLY on these results."
                try:
                    final_message = self.llm.generate(summary_prompt)
                except Exception:
                    final_message = f"Executed {len(executed_tools)} tools. Output:\n" + "\n".join(results)
                    
        self.history.add({
            "user_input": user_input,
            "interpreted_intent": intent_plan.get("intent", ""),
            "tools_called": executed_tools,
            "success": success
        })
        
        return ShellResponse(
            message=final_message, tool_calls=executed_tools, success=success, follow_up_suggestions=[]
        )