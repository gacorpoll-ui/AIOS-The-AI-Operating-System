import json
import sys
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
        self.voice = None
        
    def run(self) -> None:
        self._running = True
        
        print("\nWelcome to AIOS NL Shell.")
        print("Type 'exit' or press Ctrl+D to quit.\n")
        
        while self._running:
            try:
                # Use ASCII-safe prompt for Windows console compatibility
                prefix = "[voice] aios > " if self.voice_mode else "aios > "
                try:
                    user_input = input(prefix).strip()
                except UnicodeEncodeError:
                    user_input = input("aios > ").strip()

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
        # Fallback: if LLM not loaded, try to parse direct commands
        if not self.llm.is_loaded:
            return self._direct_interpret(user_input)
            
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

    def _direct_interpret(self, user_input: str) -> ShellResponse:
        """Direct command parsing for demo mode when LLM is not loaded."""
        lower = user_input.lower().strip()

        # Handle help first
        if lower in ("help", "--help", "-h"):
            return ShellResponse(
                message=(
                    "AIOS Shell - Direct Mode (LLM not loaded)\n\n"
                    "Available commands:\n"
                    "  'show files' / 'list files'  - List current directory\n"
                    "  'show system' / 'system info' - Show system information\n"
                    "  'processes'                  - List running processes\n"
                    "  'run <command>'              - Execute shell command\n"
                    "  '--voice'                    - Toggle voice mode\n"
                    "  'exit' / 'quit'              - Exit shell\n\n"
                    "Tip: Install llama-cpp-python for full AI mode:\n"
                    "  pip install aios[llm]"
                ),
                tool_calls=[], success=True, follow_up_suggestions=[]
            )

        # Simple command mapping
        cmd_map = {
            "show files": ("list_directory", {"path": "."}),
            "list files": ("list_directory", {"path": "."}),
            "show system": ("get_system_info", {}),
            "system info": ("get_system_info", {}),
            "processes": ("list_processes", {}),
        }

        for key, (tool_name, params) in cmd_map.items():
            if key in lower:
                if tool_name == "help":
                    return ShellResponse(
                        message=(
                            "AIOS Shell - Direct Mode (LLM not loaded)\n\n"
                            "Available commands:\n"
                            "  'show files' / 'list files'  - List current directory\n"
                            "  'show system' / 'system info' - Show system information\n"
                            "  'processes'                  - List running processes\n"
                            "  'run <command>'              - Execute shell command\n"
                            "  '--voice'                    - Toggle voice mode\n"
                            "  'exit' / 'quit'              - Exit shell\n\n"
                            "Tip: Install llama-cpp-python for full AI mode:\n"
                            "  pip install aios[llm]"
                        ),
                        tool_calls=[], success=True, follow_up_suggestions=[]
                    )

                tool_obj = self.tools.get_tool(tool_name)
                if not tool_obj:
                    return ShellResponse(
                        message=f"Tool '{tool_name}' not registered.",
                        tool_calls=[], success=False, follow_up_suggestions=[]
                    )

                print_tool_call(tool_name, params)
                try:
                    tool_result = self.tools.execute(tool_name, params, confirmed=True)
                    if tool_result.success:
                        return ShellResponse(
                            message=str(tool_result.output),
                            tool_calls=[{"tool": tool_name, "params": params}],
                            success=True, follow_up_suggestions=[]
                        )
                    else:
                        return ShellResponse(
                            message=f"Error: {tool_result.error}",
                            tool_calls=[], success=False, follow_up_suggestions=[]
                        )
                except Exception as e:
                    return ShellResponse(
                        message=f"Tool execution failed: {str(e)}",
                        tool_calls=[], success=False, follow_up_suggestions=[]
                    )

        # Try 'run' command
        if lower.startswith("run "):
            cmd = user_input[4:].strip()
            print_tool_call("run_command", {"command": cmd})
            try:
                tool_result = self.tools.execute("run_command", {"command": cmd}, confirmed=True)
                if tool_result.success:
                    out = tool_result.output
                    msg = out.get("stdout", "") or out.get("stderr", "")
                    return ShellResponse(message=msg, tool_calls=[], success=True, follow_up_suggestions=[])
                return ShellResponse(message=f"Error: {tool_result.error}", tool_calls=[], success=False, follow_up_suggestions=[])
            except Exception as e:
                return ShellResponse(message=f"Command failed: {str(e)}", tool_calls=[], success=False, follow_up_suggestions=[])

        return ShellResponse(
            message=(
                f"Demo mode: I don't understand '{user_input}'.\n"
                "Type 'help' for available commands, or install llama-cpp-python for full AI mode."
            ),
            tool_calls=[], success=False, follow_up_suggestions=["help"]
        )

def main():
    """Entry point for aios-shell command."""
    import os
    os.makedirs(os.path.expanduser("~/.aios"), exist_ok=True)

    llm = LocalLLM()
    memory = MemoryEngine(db_path=os.path.expanduser("~/.aios/shell_memory"))
    tools = ToolRegistry(db_path=os.path.expanduser("~/.aios/shell_tools.db"))

    # Register available tools
    from agent.tools.filesystem_tools import read_file, write_file, list_directory, search_files, get_file_info
    from agent.tools.process_tools import list_processes, get_process_info, kill_process, run_command
    from agent.tools.system_tools import get_system_info, get_network_info, get_installed_packages, read_logs
    from agent.core.tool_registry import Tool

    tools.register(Tool("read_file", "Read a file", {"type": "object", "properties": {"path": {"type": "string"}, "max_lines": {"type": "integer"}}}), read_file)
    tools.register(Tool("write_file", "Write to a file", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}, requires_confirmation=True), write_file)
    tools.register(Tool("list_directory", "List directory contents", {"type": "object", "properties": {"path": {"type": "string"}, "show_hidden": {"type": "boolean"}}}), list_directory)
    tools.register(Tool("search_files", "Search for files", {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "file_type": {"type": "string"}}}), search_files)
    tools.register(Tool("get_file_info", "Get file information", {"type": "object", "properties": {"path": {"type": "string"}}}), get_file_info)
    tools.register(Tool("list_processes", "List running processes", {"type": "object", "properties": {"sort_by": {"type": "string"}}}), list_processes)
    tools.register(Tool("get_process_info", "Get process details", {"type": "object", "properties": {"pid": {"type": "integer"}}}), get_process_info)
    tools.register(Tool("kill_process", "Kill a process", {"type": "object", "properties": {"pid": {"type": "integer"}, "signal_type": {"type": "string"}}}, requires_confirmation=True), kill_process)
    tools.register(Tool("run_command", "Run a shell command", {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}, "cwd": {"type": "string"}}}, requires_confirmation=True), run_command)
    tools.register(Tool("get_system_info", "Get system information", {"type": "object", "properties": {}}), get_system_info)
    tools.register(Tool("get_network_info", "Get network information", {"type": "object", "properties": {}}), get_network_info)
    tools.register(Tool("get_installed_packages", "List installed Python packages", {"type": "object", "properties": {}}), get_installed_packages)
    tools.register(Tool("read_logs", "Read log file", {"type": "object", "properties": {"log_file": {"type": "string"}, "last_n_lines": {"type": "integer"}}}), read_logs)

    shell = NLShell(llm=llm, tools=tools, memory=memory)

    # Check for --voice flag
    if "--voice" in sys.argv:
        shell.voice_mode = True
        try:
            from shell.voice_interface import VoiceInterface
            shell.voice = VoiceInterface()
        except ImportError:
            print("[warning] Voice dependencies not installed. Voice mode disabled.")
            shell.voice_mode = False

    try:
        shell.run()
    except KeyboardInterrupt:
        print("\n")
    finally:
        memory.close()
        print("Session saved. Goodbye.")

if __name__ == "__main__":
    main()