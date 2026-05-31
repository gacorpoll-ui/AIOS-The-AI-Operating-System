import sys
import re
import time
import threading
from typing import Dict, List, Any, Optional

# Strip emoji and other non-ASCII characters for Windows console compatibility
def _safe_text(text: str) -> str:
    """Remove emoji and other characters that Windows console can't display."""
    if sys.platform == 'win32':
        # Remove emoji and other high Unicode characters
        return re.sub(r'[^\x00-\x7F]', '', text)
    return text

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

# A simple fallback implementation for environments without Rich
class SimpleDisplay:
    @staticmethod
    def print_response(response: Any) -> None:
        print(f"\n{response.message}\n")
        
    @staticmethod
    def print_table(data: List[Dict[str, Any]]) -> None:
        if not data:
            print("No data.")
            return
            
        keys = list(data[0].keys())
        header = " | ".join(keys)
        print(f"\n{header}")
        print("-" * len(header))
        for item in data:
            row = " | ".join(str(item.get(k, "")) for k in keys)
            print(row)
        print()
            
    @staticmethod
    def print_error(error: str) -> None:
        print(f"\n[ERROR] {error}\n", file=sys.stderr)
        
    @staticmethod
    def print_confirmation_prompt(action: str) -> bool:
        print(f"\n⚠️  This will {action}.")
        answer = input("Continue? [y/N]: ")
        return answer.lower() == 'y'
        
    @staticmethod
    def print_tool_call(tool_name: str, params: Dict[str, Any]) -> None:
        print(f" [system] calling tool '{tool_name}'...")

# The rich implementation
def print_response(response: Any) -> None:
    if not RICH_AVAILABLE:
        SimpleDisplay.print_response(response)
        return

    if response.message:
        msg = _safe_text(response.message)
        if response.success is False:
            console.print(Panel(msg, border_style="red", title="Error"))
        else:
            console.print(f"\n{msg}\n")

    if getattr(response, "follow_up_suggestions", None):
        console.print("[dim italic]Suggestions:[/dim italic]")
        for suggestion in response.follow_up_suggestions:
            console.print(f"[dim]- {_safe_text(suggestion)}[/dim]")
            
def print_table(data: List[Dict[str, Any]], title: str = "") -> None:
    if not RICH_AVAILABLE:
        SimpleDisplay.print_table(data)
        return
        
    if not data:
        console.print("[dim]No data to display.[/dim]")
        return
        
    table = Table(title=title, show_header=True, header_style="bold magenta")
    
    # Add columns based on first item
    keys = list(data[0].keys())
    for key in keys:
        table.add_column(str(key))
        
    # Add rows
    for item in data:
        row = [str(item.get(k, "")) for k in keys]
        table.add_row(*row)
        
    console.print(table)
    
def print_error(error: str) -> None:
    if not RICH_AVAILABLE:
        SimpleDisplay.print_error(error)
        return
    console.print(f"[bold red]Error:[/bold red] {error}", style="red")
    
def print_confirmation_prompt(action: str) -> bool:
    if not RICH_AVAILABLE:
        return SimpleDisplay.print_confirmation_prompt(action)
        
    console.print(Panel(f"[bold yellow]WARNING[/bold yellow]\n\nThis will {action}.", border_style="yellow"))
    answer = input("Continue? [y/N]: ")
    return answer.lower() == 'y'
    
def print_tool_call(tool_name: str, params: Dict[str, Any]) -> None:
    if not RICH_AVAILABLE:
        SimpleDisplay.print_tool_call(tool_name, params)
        return
    
    # Format parameters concisely
    param_str = ", ".join(f"{k}={v}" for k, v in params.items())
    if len(param_str) > 50:
        param_str = param_str[:47] + "..."
        
    console.print(f"[dim grey]executing: {tool_name}({param_str})[/dim grey]")

# Spinner context manager for long running ops
class ThinkSpinner:
    def __init__(self, message: str = "Thinking..."):
        self.message = message
        self.running = False
        self.thread = None
        
    def _spin(self):
        spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while self.running:
            sys.stdout.write(f"\r\033[90m{spinner_chars[i]} {self.message}\033[0m")
            sys.stdout.flush()
            time.sleep(0.1)
            i = (i + 1) % len(spinner_chars)
            
    def __enter__(self):
        if not RICH_AVAILABLE:
            self.running = True
            self.thread = threading.Thread(target=self._spin)
            self.thread.daemon = True
            self.thread.start()
            return self
            
        # For Rich we just use the built in status context, but wrapping it
        # makes the interface simpler. In a real app we'd yield the status object.
        self._status = console.status(f"[dim]{self.message}[/dim]", spinner="dots")
        self._status.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not RICH_AVAILABLE:
            self.running = False
            if self.thread:
                self.thread.join()
            sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
            sys.stdout.flush()
        else:
            self._status.stop()
