# AIOS Master Prompt Guide
## Semua prompt siap-pakai untuk Claude Code

---

# ═══════════════════════════════════════════
# PROMPT 0 — INISIALISASI REPO (Jalankan Pertama Kali)
# ═══════════════════════════════════════════

```
You are building AIOS — an AI Operating System where AI is the kernel, not an app.

Before writing any code, explore the current directory structure and understand what exists.

Then scaffold the complete monorepo structure for AIOS with these exact directories:

aios/
├── CLAUDE.md
├── .claude/agents/ and .claude/rules/
├── kernel/          ← Rust: system layer
├── agent/core/      ← Python: orchestrator, memory, planner, tool_registry
├── agent/tools/     ← Python: individual tool implementations
├── agent/models/    ← Python: LLM interface
├── agent/tests/
├── shell/           ← Python: natural language shell
├── gui/             ← Rust: Wayland compositor (placeholder)
├── security/        ← Python+Rust: security layer
├── config/
├── docs/
├── scripts/
├── tests/integration/ and tests/e2e/
├── .github/workflows/

For each directory, create:
1. A proper README.md explaining the module's purpose and responsibilities
2. A placeholder __init__.py or mod.rs with module-level docstring
3. A .gitkeep where needed

Also create:
- pyproject.toml (Python 3.11+, with dependencies: llama-cpp-python, chromadb, langchain-core, whisper, rich, prompt_toolkit, pytest, ruff, mypy)
- Cargo.toml workspace root
- .gitignore (Python + Rust + OS files)
- .github/workflows/ci.yml (run pytest + cargo test on push)
- docs/ARCHITECTURE.md (high-level system design)
- docs/SPRINT.md (current sprint tasks)

After scaffolding, run: find . -type f | sort
to verify the structure is correct.

Constraints:
- Python 3.11+
- Rust edition 2021
- No placeholder code that looks like it works but doesn't — use TODO comments instead
- All files must have proper headers with module description
```

---

# ═══════════════════════════════════════════
# PROMPT 1 — LOCAL LLM INTEGRATION
# ═══════════════════════════════════════════

```
Goal: Integrate a local LLM into AIOS so the AI layer can run inference on-device.

Context: We're building an AI OS. The LLM is the "brain" — it needs to run locally, 
fast, with no internet requirement. We'll use llama.cpp Python bindings.

Explore agent/models/ first, then implement:

FILE: agent/models/llm_interface.py
- Class: LocalLLM
- Method: load(model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1)
  → loads GGUF model via llama-cpp-python
- Method: generate(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str
  → runs inference, returns text
- Method: generate_structured(prompt: str, schema: dict) -> dict
  → forces JSON output matching schema using grammar-based sampling
- Method: embed(text: str) -> list[float]
  → returns embedding vector for memory system
- Property: is_loaded -> bool
- Property: model_info -> dict (name, context_size, quantization)

FILE: agent/models/model_manager.py
- Class: ModelManager
- Manages multiple models (main LLM + embedding model)
- Method: download_model(model_id: str, destination: str) → downloads from HuggingFace
- Method: list_available_models() -> list[dict]
- Method: get_recommended_model(vram_gb: float) -> str
  → returns best model name for available VRAM

FILE: agent/models/prompt_templates.py
- SYSTEM_PROMPT_SHELL: str — system prompt for NL shell role
- SYSTEM_PROMPT_AGENT: str — system prompt for agent role
- SYSTEM_PROMPT_SECURITY: str — system prompt for security monitor role
- Function: build_tool_prompt(tools: list[dict]) -> str

FILE: agent/tests/test_llm_interface.py
- Unit tests for LocalLLM (mock the llama-cpp calls)
- Test: model loads correctly
- Test: generate returns string
- Test: generate_structured returns valid JSON
- Test: embed returns list of floats

After implementing, run: pytest agent/tests/test_llm_interface.py -v
Fix any failures before finishing.

Constraints:
- Handle model not found gracefully (FileNotFoundError with helpful message)
- Handle out-of-memory gracefully
- Log inference time for every call (use Python logging module)
- No global state — all state inside class instances
- Type hints on everything
```

---

# ═══════════════════════════════════════════
# PROMPT 2 — MEMORY SYSTEM
# ═══════════════════════════════════════════

```
Goal: Build AIOS persistent memory — the OS remembers context across reboots.

Context: Unlike a chatbot that forgets, AIOS maintains persistent semantic memory.
When user says "continue yesterday's work", the OS knows exactly what that means.
Memory has two layers: fast key-value (SQLite) and semantic vector search (ChromaDB).

Explore agent/core/ and agent/models/ first to understand existing code.

Implement:

FILE: agent/core/memory.py
- Class: MemoryEngine
- __init__(db_path: str, collection_name: str = "aios_memory")
  → initializes ChromaDB client + SQLite connection
- Method: store(content: str, metadata: dict, memory_type: str = "episodic") -> str
  → embeds content, stores in ChromaDB, returns memory_id
  → memory_type options: "episodic" | "semantic" | "procedural" | "working"
- Method: recall(query: str, n_results: int = 5, memory_type: str = None) -> list[dict]
  → semantic search, returns [{content, metadata, relevance_score, timestamp}]
- Method: store_kv(key: str, value: any) -> None
  → stores key-value in SQLite (for fast lookup: user prefs, system state)
- Method: get_kv(key: str, default=None) -> any
  → retrieves from SQLite
- Method: get_context_summary(last_n_hours: int = 24) -> str
  → returns AI-generated summary of recent activity
- Method: forget(memory_id: str) -> None
  → removes specific memory (GDPR-like control)
- Method: forget_all(memory_type: str = None) -> int
  → wipe memories by type, returns count deleted

FILE: agent/core/context_manager.py
- Class: ContextManager
- Maintains the "working context" of the current session
- Method: start_session() -> str (session_id)
- Method: add_event(event_type: str, data: dict) -> None
  → records: command_executed, file_opened, error_occurred, task_completed
- Method: get_current_context() -> dict
  → returns: {active_task, open_files, recent_commands, session_duration}
- Method: save_session() -> None
  → persists session to MemoryEngine before shutdown
- Method: restore_last_session() -> dict
  → loads most recent session context

FILE: agent/tests/test_memory.py
- Test: store and recall returns correct content
- Test: recall with query returns semantically relevant results
- Test: kv store persists across MemoryEngine instances
- Test: forget removes memory
- Test: context_manager session save/restore

Run: pytest agent/tests/test_memory.py -v
All tests must pass.

Constraints:
- ChromaDB must use persistent client (not in-memory) for actual persistence
- SQLite WAL mode for concurrent access
- All timestamps in UTC ISO 8601
- Memory content encrypted at rest using Fernet (from cryptography library)
- Max memory entry size: 10,000 characters (chunk larger content)
```

---

# ═══════════════════════════════════════════
# PROMPT 3 — TOOL REGISTRY & SYSTEM TOOLS
# ═══════════════════════════════════════════

```
Goal: Build the tool system — how AI accesses OS capabilities safely.

Context: The AI needs to interact with the OS: read files, run commands, check processes.
Every tool must be sandboxed, logged, and require explicit permission for dangerous ops.
Tools follow the MCP (Model Context Protocol) pattern: name, description, input_schema, execute().

Explore agent/core/ and agent/tools/ first.

Implement:

FILE: agent/core/tool_registry.py
- Class: Tool (dataclass)
  → fields: name, description, input_schema (JSON schema dict), requires_confirmation: bool
- Class: ToolRegistry
- Method: register(tool: Tool, handler: callable) -> None
- Method: get_tool(name: str) -> Tool | None
- Method: list_tools() -> list[dict]  ← returns OpenAI-compatible function specs
- Method: execute(tool_name: str, params: dict, confirmed: bool = False) -> ToolResult
  → if tool.requires_confirmation and not confirmed: raise ConfirmationRequired
  → logs all executions to SQLite
  → wraps in try/except, returns ToolResult(success, output, error)
- Class: ToolResult (dataclass)
  → fields: success: bool, output: any, error: str | None, execution_time_ms: int

FILE: agent/tools/filesystem_tools.py
- Tool: read_file(path: str, max_lines: int = 500) -> str
- Tool: write_file(path: str, content: str) → requires_confirmation=True
- Tool: list_directory(path: str, show_hidden: bool = False) -> list[dict]
- Tool: search_files(query: str, path: str = ".", file_type: str = None) -> list[str]
  → semantic search using embeddings if query is natural language
  → glob search if query contains * or ?
- Tool: get_file_info(path: str) -> dict (size, modified, permissions, type)

FILE: agent/tools/process_tools.py
- Tool: list_processes(sort_by: str = "cpu") -> list[dict]
- Tool: get_process_info(pid: int) -> dict
- Tool: kill_process(pid: int, signal: str = "SIGTERM") → requires_confirmation=True
- Tool: run_command(command: str, timeout: int = 30, cwd: str = None) -> dict
  → runs in subprocess with timeout, captures stdout/stderr
  → BLOCKS: rm -rf /, sudo rm, dd if=/dev/zero, mkfs (safety check)
  → requires_confirmation=True for any sudo command

FILE: agent/tools/system_tools.py
- Tool: get_system_info() -> dict (cpu%, memory%, disk%, uptime, hostname)
- Tool: get_network_info() -> dict (interfaces, ips, connection status)
- Tool: get_installed_packages() -> list[str]
- Tool: read_logs(log_file: str, last_n_lines: int = 100) -> str

FILE: agent/tests/test_tools.py
- Test: registry registers and retrieves tools
- Test: execute returns ToolResult
- Test: dangerous commands require confirmation
- Test: blocked commands are rejected
- Test: read_file works for existing file, raises for missing
- Test: list_processes returns list with required fields

Run: pytest agent/tests/test_tools.py -v

Constraints:
- NEVER use shell=True in subprocess calls (use list args)
- All file paths must be resolved to absolute and checked against allowed_roots
- Timeout on ALL subprocess calls (default 30s, max 300s)
- Log every tool call: tool_name, params, result_success, execution_time
- Tools must be importable without any OS-specific dependencies failing
```

---

# ═══════════════════════════════════════════
# PROMPT 4 — NATURAL LANGUAGE SHELL
# ═══════════════════════════════════════════

```
Goal: Build the NL Shell — the primary user interface of AIOS.
Replace bash with a shell that understands natural language.

Context: User types "show me the 5 biggest files in my home folder" 
→ AI understands intent → calls list_directory + sorts → presents results nicely.
It's not just a chatbot — it executes real OS operations based on intent.

Explore shell/, agent/core/, agent/tools/ first.

Implement:

FILE: shell/nl_shell.py
- Class: NLShell
- __init__(llm: LocalLLM, tools: ToolRegistry, memory: MemoryEngine)
- Method: run() → main REPL loop
  → shows prompt: "aios ❯ "
  → reads input (prompt_toolkit for rich editing, history, autocomplete)
  → calls interpret(user_input)
  → displays result
  → Ctrl+C: cancel current operation (not exit)
  → Ctrl+D: graceful exit
- Method: interpret(user_input: str) -> ShellResponse
  → calls LLM with tool definitions in context
  → parses LLM response (may call 0, 1, or multiple tools)
  → for each tool call: check if requires_confirmation, ask user if so
  → executes tools in sequence or parallel as needed
  → calls LLM again with tool results to generate final response
  → returns ShellResponse
- Class: ShellResponse (dataclass)
  → fields: message: str, tool_calls: list, success: bool, follow_up_suggestions: list[str]

FILE: shell/display.py
- Uses `rich` library for beautiful terminal output
- Function: print_response(response: ShellResponse) → formatted output
- Function: print_table(data: list[dict]) → rich table
- Function: print_error(error: str) → red formatted error
- Function: print_confirmation_prompt(action: str) -> bool
  → shows: "⚠️  This will [action]. Continue? [y/N]"
- Function: print_thinking() → shows animated spinner while AI processes
- Function: print_tool_call(tool_name: str, params: dict) → dim grey inline

FILE: shell/history.py
- Class: ShellHistory
- Stores: input, interpreted_intent, tools_called, timestamp
- Method: add(entry: dict) → saves to SQLite
- Method: get_recent(n: int = 20) -> list[dict]
- Method: search(query: str) -> list[dict] ← semantic search on past commands

FILE: shell/safety.py
- Class: SafetyChecker
- Method: check_intent(user_input: str, planned_tools: list) -> SafetyResult
  → detects if intent is dangerous: mass deletion, system modification, exfiltration
- Method: require_confirmation(action_description: str) -> bool
  → presents clear confirmation prompt
- Patterns to always block: format/wipe disk, delete home directory

FILE: shell/tests/test_nl_shell.py
- Test: interpret simple command returns ShellResponse
- Test: dangerous command triggers confirmation
- Test: blocked command is rejected
- Test: history records commands
- Test: multi-step command executes tools in correct order

Run: pytest shell/tests/ -v

Constraints:
- Shell must work in terminal without GUI
- Graceful degradation if LLM is not loaded (show error, suggest fix)
- All tool confirmations must be explicit [y/N] — default is NO
- Session history persists between shell restarts
- Response time target: < 3 seconds for simple commands (show spinner for longer)
```

---

# ═══════════════════════════════════════════
# PROMPT 5 — AGENT ORCHESTRATOR
# ═══════════════════════════════════════════

```
Goal: Build the Agent Orchestrator — lets AIOS handle complex multi-step goals autonomously.

Context: User says "set up a Python dev environment, install my requirements.txt, 
run the tests, and tell me what failed." This requires: multiple tool calls, 
conditional logic, error handling, and a final summary. The orchestrator handles this.

Explore agent/core/, agent/tools/, agent/models/ first.

Implement:

FILE: agent/core/orchestrator.py
- Class: AgentOrchestrator
- __init__(llm: LocalLLM, tools: ToolRegistry, memory: MemoryEngine, planner: Planner)
- Method: run(goal: str, context: dict = None) -> AgentResult
  → main agentic loop (max 20 iterations before stopping)
  → Plan → Execute → Observe → Reflect → Repeat
  → stops when: goal achieved, max iterations hit, or unrecoverable error
- Method: _plan(goal: str, context: dict) -> ExecutionPlan
- Method: _execute_step(step: PlanStep) -> StepResult
- Method: _reflect(steps_so_far: list[StepResult], goal: str) -> ReflectionResult
  → LLM assesses: is goal achieved? what's next? any blockers?
- Method: _handle_error(step: PlanStep, error: Exception) -> ErrorAction
  → ErrorAction: RETRY | SKIP | ABORT | REPLAN

FILE: agent/core/planner.py
- Class: Planner
- Method: create_plan(goal: str, available_tools: list, context: dict) -> ExecutionPlan
  → uses LLM to break goal into ordered steps
- Class: ExecutionPlan (dataclass)
  → fields: goal, steps: list[PlanStep], estimated_duration: str, risks: list[str]
- Class: PlanStep (dataclass)
  → fields: step_id, description, tool_name, tool_params, depends_on: list[str], requires_confirmation: bool
- Method: replan(original_plan, failed_step, error_msg) -> ExecutionPlan
  → adapts plan when a step fails

FILE: agent/core/executor.py
- Class: ParallelExecutor
- Method: execute_plan(plan: ExecutionPlan, on_step_complete: callable = None) -> list[StepResult]
  → executes steps respecting dependencies
  → runs independent steps in parallel (ThreadPoolExecutor)
  → calls on_step_complete callback after each step (for live progress)
- Class: StepResult (dataclass)
  → fields: step_id, success, output, error, duration_ms

FILE: agent/tests/test_orchestrator.py
- Test: simple single-tool goal executes correctly
- Test: multi-step goal executes steps in dependency order
- Test: failed step triggers replan
- Test: max iterations limit prevents infinite loops
- Test: goal achieved detection stops loop

Run: pytest agent/tests/test_orchestrator.py -v

Constraints:
- Every step must be logged with timing (docs/SPRINT.md pattern)
- Orchestrator MUST show progress to user (callback pattern, not silent)
- Parallel execution max workers: 4 (prevent resource exhaustion)
- Any step with requires_confirmation=True pauses and asks user
- Total orchestration timeout: 10 minutes (configurable)
- Orchestrator state is checkpointed every 5 steps (for recovery)
```

---

# ═══════════════════════════════════════════
# PROMPT 6 — SECURITY LAYER
# ═══════════════════════════════════════════

```
Goal: Build AIOS security layer — AI-powered threat detection and privacy protection.

Context: Because AI can execute OS commands, security is critical. 
We need: sandboxing, behavioral monitoring, encrypted memory vault, 
and permission management. This is NOT optional — it ships in Phase 1.

Explore security/, agent/core/, agent/tools/ first.

Implement:

FILE: security/monitor.py
- Class: SecurityMonitor
- Method: start() → starts background monitoring thread
- Method: stop()
- Method: on_tool_call(tool_name: str, params: dict) -> SecurityDecision
  → checks against threat patterns
  → returns: SecurityDecision(allowed: bool, reason: str, risk_level: str)
- Method: analyze_behavior(recent_actions: list[dict]) -> ThreatAssessment
  → uses LLM or heuristics to detect: data exfiltration, mass deletion, lateral movement
- Method: get_threat_log() -> list[dict]

FILE: security/sandbox.py
- Class: CommandSandbox
- Method: run_sandboxed(command: list[str], timeout: int, allowed_paths: list[str]) -> SandboxResult
  → uses Python subprocess with:
    - resource limits (max memory, max CPU time)
    - restricted file access (chroot-like via allowed_paths check)
    - network disabled (via env manipulation)
    - timeout enforced
- Blocked command patterns (regex list):
  → rm -rf /, sudo rm -rf, mkfs, dd if=/dev/zero, :(){ :|:& };: (fork bomb)
- Method: validate_path(path: str, allowed_roots: list[str]) -> bool

FILE: security/vault.py
- Class: SecureVault
- Uses Fernet symmetric encryption (from cryptography library)
- Method: store_secret(key: str, value: str) → encrypts and stores in vault.db
- Method: get_secret(key: str) -> str | None → decrypts and returns
- Method: delete_secret(key: str) -> bool
- Method: list_keys() -> list[str]  ← returns key names only, never values
- Key derivation: PBKDF2HMAC from user passphrase + salt stored in ~/.aios/

FILE: security/permissions.py
- Class: PermissionManager
- Capability-based permission system
- Permissions: FILE_READ, FILE_WRITE, PROCESS_KILL, NETWORK_ACCESS, SYSTEM_MODIFY
- Method: grant(tool_name: str, permission: Permission) → stored in SQLite
- Method: revoke(tool_name: str, permission: Permission)
- Method: check(tool_name: str, permission: Permission) -> bool
- Method: require(tool_name: str, permission: Permission) 
  → raises PermissionDenied if not granted

FILE: security/tests/test_security.py
- Test: blocked commands are rejected by sandbox
- Test: path traversal attempts are caught
- Test: vault encrypts (stored value != original)
- Test: vault decrypts correctly
- Test: permission check works for granted/revoked

Run: pytest security/tests/ -v

Constraints:
- SecurityMonitor runs in separate thread — must be thread-safe
- Vault key never stored in plaintext anywhere
- Permission grants must survive restart (SQLite persistent)
- All security decisions must be logged with timestamp
- Security layer must add < 50ms overhead to normal operations
```

---

# ═══════════════════════════════════════════
# PROMPT 7 — AI DAEMON (Background Service)
# ═══════════════════════════════════════════

```
Goal: Build the AI Daemon — the always-on background intelligence of AIOS.

Context: The daemon runs continuously, watching system state, anticipating needs,
and being ready to respond instantly when user interacts. Like a brain that never sleeps.

Explore agent/core/, security/, and existing daemons pattern in Linux.

Implement:

FILE: agent/core/daemon.py
- Class: AIOSDaemon
- Runs as a background process (asyncio event loop)
- Method: start() → initializes all subsystems, starts event loop
- Method: stop() → graceful shutdown, saves state
- Subsystems initialized:
  → LLM (warm — model pre-loaded)
  → MemoryEngine
  → ContextManager  
  → ToolRegistry (all tools registered)
  → SecurityMonitor
  → SystemWatcher
- Method: handle_shell_request(request: dict) -> dict
  → IPC handler: shell sends requests via Unix socket
  → routes to orchestrator or NL shell interpreter
  → returns response dict

FILE: agent/core/system_watcher.py
- Class: SystemWatcher
- Monitors system state continuously (polling every 30s)
- Tracks: CPU%, Memory%, Disk%, Running processes, Network activity
- Method: get_current_state() -> SystemState
- Method: detect_anomaly(state: SystemState) -> list[Anomaly]
  → high CPU (>90% for 2+ min), low disk (<5%), suspicious new process
- Method: predict_resource_needs(history: list[SystemState]) -> Prediction
  → simple heuristic: same time yesterday usage + trend

FILE: agent/core/ipc.py
- Class: IPCServer
- Unix socket server (path: /tmp/aios.sock)
- Method: start_server() → asyncio server
- Method: handle_client(reader, writer)
  → protocol: JSON lines (one JSON object per line)
  → request format: {"id": str, "type": str, "payload": dict}
  → response format: {"id": str, "success": bool, "data": any, "error": str|null}
- Class: IPCClient
- Method: send(request_type: str, payload: dict) -> dict
  → connects to daemon socket, sends request, returns response

FILE: scripts/aios-daemon.service (systemd unit file)
[Unit]
Description=AIOS AI Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/aios/agent/core/daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

FILE: scripts/start_daemon.sh → starts daemon with proper env
FILE: scripts/stop_daemon.sh → graceful stop via IPC
FILE: scripts/daemon_status.sh → shows daemon status and last 20 log lines

FILE: agent/tests/test_daemon.py
- Test: daemon starts and IPC socket is created
- Test: IPC client can connect and ping daemon
- Test: system watcher returns valid SystemState
- Test: anomaly detection fires on simulated high CPU

Run: pytest agent/tests/test_daemon.py -v

Constraints:
- Daemon must handle SIGTERM gracefully (save state before exit)
- All daemon logs to /var/log/aios/daemon.log with rotation
- IPC protocol must be versioned (include "version": "1.0" in all messages)
- Daemon startup time target: < 10 seconds (model pre-load in background)
- Daemon memory footprint target: < 2GB (with quantized 7B model loaded)
```

---

# ═══════════════════════════════════════════
# PROMPT 8 — CI/CD & GITHUB SETUP
# ═══════════════════════════════════════════

```
Goal: Set up complete GitHub CI/CD pipeline for AIOS.

Explore .github/ and existing test files first.

Implement:

FILE: .github/workflows/ci.yml
- Trigger: push to main, all pull requests
- Jobs:
  1. lint-python:
     → runs: ruff check . && mypy agent/ shell/ security/
  2. test-python:
     → matrix: ubuntu-latest, python 3.11 and 3.12
     → runs: pytest with coverage (target: 70% minimum)
     → uploads coverage report as artifact
  3. test-rust:
     → runs: cargo fmt --check && cargo clippy && cargo test
  4. security-scan:
     → runs: pip-audit (check Python deps for CVEs)
     → runs: cargo audit (check Rust deps for CVEs)
  5. build-check:
     → runs: python -m build (verify package builds)

FILE: .github/workflows/release.yml
- Trigger: push tag v*.*.* 
- Creates GitHub Release with:
  → Changelog from git log
  → Python wheel artifact
  → Rust binary artifact

FILE: .github/PULL_REQUEST_TEMPLATE.md
- Checklist: tests added, docs updated, security considered

FILE: .github/ISSUE_TEMPLATE/bug_report.md
FILE: .github/ISSUE_TEMPLATE/feature_request.md

FILE: pyproject.toml (complete, production-ready)
- [project] section with all metadata
- [project.scripts] aios-shell, aios-daemon
- [tool.ruff] with appropriate rules
- [tool.mypy] strict mode
- [tool.pytest.ini_options] with coverage settings

FILE: README.md (compelling, complete)
- Project description and vision
- Architecture diagram (ASCII)
- Quick start (5 commands to get running)
- Feature list
- Tech stack
- Contributing guide
- License badge (MIT)

After creating all files, run:
git add -A
git status

(do NOT git commit — let user review first)

Verify CI would pass by running locally:
ruff check . --statistics
pytest agent/ shell/ security/ --co -q  ← just collect, don't run
```

---

# ═══════════════════════════════════════════
# PROMPT 9 — REVIEW & REFACTOR SESSION
# ═══════════════════════════════════════════

```
You are doing a comprehensive code review of the AIOS codebase.

First, explore the entire project structure:
find . -name "*.py" | head -50
find . -name "*.rs" | head -20

Then for each major module (agent/core/, shell/, security/):

1. READ the implementation files
2. IDENTIFY issues in these categories:
   - Type safety (missing type hints, wrong types)
   - Error handling (bare except, swallowed errors, missing timeout)
   - Security (any hardcoded paths, missing input validation, shell injection risk)
   - Performance (blocking calls in async context, N+1 queries, missing caching)
   - Test coverage (critical paths not tested)
   - Documentation (missing docstrings on public methods)

3. For each issue found, create a fix:
   - Small fixes: apply immediately
   - Large refactors: create a GitHub issue description in docs/ISSUES.md

4. After fixing, run the full test suite:
   pytest agent/ shell/ security/ -v --tb=short

5. Generate a review summary in docs/CODE_REVIEW.md:
   - Issues found by category
   - Fixes applied
   - Remaining items for next sprint
   - Overall code health score (1-10 with justification)

Constraints:
- Fix one file at a time, run tests after each fix
- Never break existing passing tests
- If unsure about a fix, document it in ISSUES.md instead of guessing
- Ask me before any large architectural changes
```

---

# ═══════════════════════════════════════════
# PROMPT 10 — FEATURE: VOICE INTERFACE
# ═══════════════════════════════════════════

```
Goal: Add voice control to AIOS NL Shell.
User can speak commands, AI responds via text-to-speech.

Explore shell/ and agent/models/ first.

Implement:

FILE: shell/voice_interface.py
- Class: VoiceInterface
- Uses: openai-whisper (local, no API needed) for STT
- Uses: pyttsx3 or espeak for TTS (offline)
- Method: listen(timeout: int = 10) -> str | None
  → records from microphone until silence (using sounddevice)
  → transcribes with Whisper (base model by default)
  → returns transcribed text or None if nothing detected
- Method: speak(text: str, speed: float = 1.0) -> None
  → converts text to speech, plays audio
  → strips markdown formatting before speaking
- Method: start_continuous(callback: callable) -> None
  → background thread: listens → transcribes → calls callback(text)
- Property: is_available -> bool (checks if microphone exists)

FILE: shell/nl_shell.py (modify existing)
- Add --voice flag to enable voice mode
- When voice mode active:
  → prompt shows 🎙️ instead of ❯
  → after AI response, speak the response aloud
  → Ctrl+V: toggle voice on/off during session

FILE: shell/tests/test_voice.py
- Test: VoiceInterface.is_available returns bool
- Test: speak() completes without error (mock pyttsx3)
- Test: voice mode flag changes shell behavior

Run: pytest shell/tests/test_voice.py -v

Constraints:
- Voice is OPTIONAL — shell works fine without it
- Whisper model: "base" by default (fast, low RAM), configurable
- TTS must work offline
- Never send audio data anywhere
- Handle "no microphone" gracefully
```

---

# ═══════════════════════════════════════════
# TIPS: CARA PAKAI PROMPT INI DI CLAUDE CODE
# ═══════════════════════════════════════════

## Setup Awal
```bash
# 1. Install Claude Code
npm install -g @anthropic-ai/claude-code

# 2. Buat folder repo
mkdir aios && cd aios
git init

# 3. Copy CLAUDE.md ke root repo
cp /path/to/CLAUDE.md .

# 4. Start Claude Code
claude

# 5. Jalankan PROMPT 0 pertama kali (copy-paste konten prompt)
```

## Urutan Prompt yang Benar
1. PROMPT 0 — Scaffold dulu, jangan skip
2. PROMPT 1 — LLM interface (fondasi semua AI)
3. PROMPT 2 — Memory (dibutuhkan semua layer)
4. PROMPT 3 — Tools (dibutuhkan shell & agent)
5. PROMPT 4 — NL Shell (bisa test interaktif di sini)
6. PROMPT 5 — Agent Orchestrator (level up dari shell)
7. PROMPT 6 — Security (paralel dengan 4 & 5 bisa)
8. PROMPT 7 — Daemon (integrates everything)
9. PROMPT 8 — CI/CD (sebelum push ke GitHub)
10. PROMPT 9 — Review (sebelum release)

## Tips Claude Code
- Selalu mulai session dengan: `explore the project structure first`
- Setelah setiap prompt: `run the tests and fix any failures`
- Sebelum commit: `review the changes and check for security issues`
- Gunakan Plan Mode (`/plan`) untuk prompt kompleks
- Gunakan `/compact` jika context terlalu panjang

## GitHub Push Flow
```bash
# Setelah PROMPT 8 selesai
git add -A
git commit -m "feat: initial AIOS scaffold"
git remote add origin https://github.com/username/aios.git
git push -u origin main
```
