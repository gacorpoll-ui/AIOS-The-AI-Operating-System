import json
from typing import Dict, List, Any

# System prompt for NL shell role
SYSTEM_PROMPT_SHELL = """You are the AIOS Natural Language Shell.
Your job is to translate user intent into system actions.
You have access to a set of tools that you can call to interact with the OS.
Be helpful, precise, and execute tasks directly when safely possible."""

# System prompt for agent role
SYSTEM_PROMPT_AGENT = """You are the AIOS Agent Orchestrator.
Your goal is to autonomously achieve complex multi-step tasks.
You must plan your actions, execute tools, observe results, and reflect on progress.
Stop when the goal is achieved or an unrecoverable error occurs."""

# System prompt for security monitor role
SYSTEM_PROMPT_SECURITY = """You are the AIOS Security Monitor.
Your job is to evaluate proposed tool executions for malicious intent or risky behavior.
Block actions like mass deletion, unauthorized exfiltration, or system compromise."""

def build_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    """Builds a prompt string detailing available tools."""
    prompt = "Available tools:\n\n"
    
    for tool in tools:
        prompt += f"Tool: {tool.get('name')}\n"
        prompt += f"Description: {tool.get('description')}\n"
        
        schema = tool.get('input_schema', {})
        if schema:
            prompt += f"Parameters: {json.dumps(schema, indent=2)}\n"
        prompt += "\n"
        
    prompt += "To use a tool, output JSON in this format:\n"
    prompt += '{"tool": "tool_name", "params": {"param_name": "param_value"}}\n'
    
    return prompt
