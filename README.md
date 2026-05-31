# 🧠 AIOS — The AI Operating System

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)
![Rust 2021](https://img.shields.io/badge/Rust-2021-orange.svg)
![Tests](https://img.shields.io/badge/Tests-39%20Passing-brightgreen.svg)

> **AIOS** is an experimental operating system concept where the AI is the kernel, rather than just an application running on top of the OS. It provides an intelligent agent that serves as your primary interaction layer — capable of executing shell commands, planning long-running tasks, remembering context across reboots, and monitoring system health autonomously.

---

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)
- [Voice Control](#-voice-control)
- [Security Model](#-security-model)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                    User Interface                     │
│  ┌─────────────────┐    ┌──────────────────────────┐ │
│  │  NL Shell (CLI) │    │  Voice Interface (STT+TTS)│ │
│  │  (prompt_toolkit│    │  (whisper + pyttsx3)      │ │
│  │   + rich)       │    └────────────┬─────────────┘ │
│  └────────┬────────┘                 │               │
│           └──────────┬───────────────┘               │
│                      ▼                               │
│         ┌────────────────────────┐                   │
│         │    Safety Checker      │ ◄── Block threats│
│         │  (regex + heuristics)  │                   │
│         └────────────┬───────────┘                   │
│                      ▼                               │
│  ┌───────────────────────────────────────────────┐   │
│  │          Agent Orchestrator                    │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │   │
│  │  │ Planner  │→ │ Executor │→ │  Reflection  │ │   │
│  │  │  (LLM)   │  │(Parallel)│  │  (Replan?)   │ │   │
│  │  └──────────┘  └──────────┘  └──────────────┘ │   │
│  └──────────────────────┬────────────────────────┘   │
│                         ▼                             │
│  ┌───────────────────────────────────────────────┐   │
│  │              Tool Registry                     │   │
│  │  ┌────────────┐ ┌──────────┐ ┌──────────────┐ │   │
│  │  │ Filesystem │ │ Processes│ │ System Info  │ │   │
│  │  │  Tools     │ │  Tools   │ │    Tools     │ │   │
│  │  └────────────┘ └──────────┘ └──────────────┘ │   │
│  └──────────────────────┬────────────────────────┘   │
│                         ▼                             │
│  ┌───────────────────────────────────────────────┐   │
│  │           AI Daemon (Background)               │   │
│  │  ┌────────────┐  ┌──────────┐  ┌────────────┐ │   │
│  │  │ System     │  │ Security │  │ IPC Server │ │   │
│  │  │ Watcher    │  │ Monitor  │  │ (TCP/Unix) │ │   │
│  │  └────────────┘  └──────────┘  └────────────┘ │   │
│  └──────────────────────┬────────────────────────┘   │
│                         ▼                             │
│  ┌───────────────────────────────────────────────┐   │
│  │              Core Services                     │   │
│  │  ┌────────────┐  ┌──────────┐  ┌────────────┐ │   │
│  │  │  LLM       │  │ Persistent│  │ Secure     │ │   │
│  │  │ Interface  │  │  Memory   │  │  Vault     │ │   │
│  │  │(llama.cpp) │  │(Chroma+KV)│  │  (Fernet)  │ │   │
│  │  └────────────┘  └──────────┘  └────────────┘ │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **🗣️ Natural Language Shell** | REPL terminal yang memahami intent, bukan hanya perintah. Ketik "show me the 5 biggest files" dan AI akan mengeksekusi. |
| **🎙️ Voice Control** | Kontrol penuh melalui suara. Speech-to-Text dengan Whisper (offline) dan Text-to-Speech dengan pyttsx3. |
| **🧠 Persistent Semantic Memory** | OS mengingat interaksi, file, dan preferensi Anda melintasi reboot menggunakan ChromaDB (vector) + SQLite (key-value). |
| **🤖 Agent Orchestrator** | Memecah tugas kompleks menjadi langkah-langkah paralel, mengeksekusi, dan merefleksikan kemajuan secara mandiri. |
| **🔒 Security Layer** | Sandbox command, behavioral anomaly detection, encrypted vault (Fernet), dan capability-based permission system. |
| **📊 System Watcher** | Daemon yang terus memantau CPU, RAM, disk, dan koneksi jaringan — mendeteksi anomali sebelum terjadi crash. |
| **🔌 IPC Server** | Komunikasi antar-proses via Unix Socket (Linux/macOS) atau TCP localhost (Windows). |
| **🧩 Tool Registry** | Ekosistem tools modular (filesystem, process, system) yang bisa diperluas dengan mudah. |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Git**
- *(Opsional)* **Rust 2021** untuk komponen kernel/GUI

### 1. Clone & Install

```bash
git clone https://github.com/gacorpoll-ui/aios.git
cd aios

# Buat virtual environment
python -m venv .venv

# Aktifkan
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dengan semua dependensi
pip install -e ".[all]"

# Atau install minimal (tanpa voice/ML deps)
pip install -e .
```

### 2. Start the AI Daemon

```bash
# Linux/macOS:
./scripts/start_daemon.sh

# Windows (PowerShell):
python -m agent.core.daemon
```

### 3. Open the NL Shell

```bash
# Mode teks standar:
aios-shell

# Atau langsung dari Python:
python -c "from shell.nl_shell import NLShell; from agent.core.daemon import AIOSDaemon; ..."
```

### 4. Enable Voice Mode *(opsional)*

```bash
# Install dependensi suara
pip install openai-whisper pyttsx3 sounddevice numpy

# Di dalam shell, ketik:
--voice
```

---

## 📁 Project Structure

```
aios/
├── agent/
│   ├── core/           # Agent orchestrator, planner, executor, IPC, daemon
│   │   ├── orchestrator.py   # ReAct loop: Plan → Execute → Reflect
│   │   ├── planner.py        # LLM-based step decomposition
│   │   ├── executor.py       # Parallel step execution with dependencies
│   │   ├── memory.py         # ChromaDB + SQLite persistent memory
│   │   ├── context_manager.py # Session context save/restore
│   │   ├── daemon.py         # Always-on background service
│   │   ├── ipc.py            # TCP/Unix socket IPC server & client
│   │   ├── system_watcher.py # CPU/RAM/disk monitoring + anomaly detection
│   │   └── tool_registry.py  # Tool registration, execution & logging
│   ├── models/         # LLM interface and prompt templates
│   │   ├── llm_interface.py  # llama-cpp-python wrapper with mock fallback
│   │   ├── model_manager.py  # Model download & VRAM recommendations
│   │   └── prompt_templates.py # System prompts for shell, agent, security
│   ├── tools/          # Individual tool implementations
│   │   ├── filesystem_tools.py # read, write, list, search, file info
│   │   ├── process_tools.py    # list, info, kill processes, run commands
│   │   └── system_tools.py     # system info, network, packages, logs
│   └── tests/          # Unit tests for agent/core (18 tests)
├── shell/
│   ├── nl_shell.py           # Natural language REPL with safety checks
│   ├── display.py            # Rich terminal output + spinner
│   ├── history.py            # SQLite command history with search
│   ├── safety.py             # Intent evaluation + forbidden pattern blocking
│   ├── voice_interface.py    # STT (Whisper) + TTS (pyttsx3)
│   └── tests/                # Unit tests for shell (10 tests)
├── security/
│   ├── monitor.py            # Background threat detection
│   ├── sandbox.py            # Command sandbox with blocked patterns
│   ├── vault.py              # Encrypted secret storage (Fernet)
│   ├── permissions.py        # Capability-based permission system
│   └── tests/                # Unit tests for security (5 tests)
├── kernel/             # Rust system layer (planned)
├── gui/                # Rust GUI compositor (planned)
├── config/             # Configuration files
├── docs/               # Architecture, sprint tracking, code reviews
├── scripts/            # Daemon management scripts
├── tests/              # Integration & E2E tests (planned)
├── .github/
│   ├── workflows/
│   │   ├── ci.yml            # Lint + test + build on PR/push
│   │   └── release.yml       # Auto-release on version tags
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
├── pyproject.toml      # Python project metadata, deps, tool configs
├── Cargo.toml          # Rust workspace definition
├── CLAUDE.md           # Master prompt guide for AI-assisted development
└── README.md           # This file
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **AI Core** | Python 3.11+ | Main logic, orchestration, tools |
| **Inference** | `llama-cpp-python` | Local GGUF model inference (offline) |
| **Semantic Memory** | `chromadb` | Vector-based semantic search |
| **Fast Storage** | `sqlite3` | Key-value store, history, permissions |
| **Encryption** | `cryptography` (Fernet) | Secret vault encryption |
| **Shell UI** | `prompt_toolkit` + `rich` | Beautiful terminal interface |
| **Voice STT** | `openai-whisper` | Offline speech recognition |
| **Voice TTS** | `pyttsx3` | Offline text-to-speech |
| **Audio I/O** | `sounddevice` + `numpy` | Microphone recording |
| **System Monitor** | `psutil` | CPU, RAM, process, network stats |
| **Testing** | `pytest` | 39 unit tests |
| **Linting** | `ruff` + `mypy` | Code quality & type checking |
| **System Layer** | Rust 2021 | Kernel & GUI (planned) |
| **CI/CD** | GitHub Actions | Automated testing & releases |

---

## 🎙️ Voice Control

AIOS mendukung kontrol suara **sepenuhnya offline** — tidak ada data audio yang dikirim ke server manapun.

### Cara Kerja

1. **Speech-to-Text (STT):** Mikrofon merekam audio 16kHz → Whisper model `base` mentranskripsi ke teks.
2. **Intent Processing:** NL Shell memproses teks seperti input keyboard biasa.
3. **Text-to-Speech (TTS):** Respons AI dibacakan keras-keras menggunakan `pyttsx3` dengan markdown yang sudah dibersihkan.

### Commands

| Command | Action |
|---------|--------|
| `--voice` | Toggle mode suara on/off |
| `Ctrl+V` | Toggle voice saat sesi berjalan |
| `Ctrl+C` | Batalkan operasi saat ini (tidak keluar) |
| `Ctrl+D` | Keluar dari shell dengan graceful exit |

### Dependencies Opsional

Voice adalah fitur **opsional**. Shell tetap berfungsi penuh tanpa instalasi dependensi suara.

```bash
# Install semua dependensi suara sekaligus
pip install openai-whisper pyttsx3 sounddevice numpy
```

---

## 🔒 Security Model

AIOS dirancang dengan prinsip **"AI cannot be trusted with root access."** Semua eksekusi command melalui beberapa lapisan pertahanan:

| Lapisan | Fungsi |
|---------|--------|
| **1. Pattern Matching** | Regex memblokir pola berbahaya (`rm -rf /`, `mkfs`, fork bomb, dll.) sebelum dieksekusi. |
| **2. Confirmation Prompts** | Command berbahaya atau yang mengubah sistem meminta konfirmasi eksplisit pengguna. |
| **3. Command Sandbox** | `subprocess.run` selalu menggunakan `shell=False`, dengan timeout 30 detik dan environment yang disanitasi. |
| **4. Path Validation** | Semua akses file divalidasi terhadap `allowed_roots` untuk mencegah directory traversal. |
| **5. Behavioral Monitor** | Thread latar belakang mendeteksi pola perilaku mencurigakan (mis. 3+ delete commands berturut-turut). |
| **6. Encrypted Vault** | Rahasia (API keys, credentials) dienkripsi dengan Fernet (PBKDF2HMAC + salt) dan disimpan di SQLite. |
| **7. Permission System** | Capability-based permissions (FILE_READ, NETWORK_ACCESS, dll.) yang tersimpan persisten di SQLite. |

---

## 🧪 Development

### Running Tests

```bash
# Jalankan seluruh test suite
pytest agent/ shell/ security/ -v

# Jalankan dengan coverage
pytest agent/ shell/ security/ --cov=agent --cov=shell --cov=security

# Jalankan test spesifik
pytest agent/tests/test_orchestrator.py -v
```

### Linting & Type Checking

```bash
# Lint dengan ruff
ruff check .

# Type check dengan mypy
mypy agent/ shell/ security/
```

### Project Configuration

Seluruh konfigurasi tooling ada di `pyproject.toml`:
- **pytest**: `testpaths = ["agent/tests", "shell/tests", "security/tests"]`
- **ruff**: `line-length = 120`, `target-version = "py311"`
- **mypy**: `python_version = "3.11"`, strict mode

---

## 🤝 Contributing

Kontribusi sangat disambut! Berikut cara memulai:

1. **Fork** repository ini
2. **Buat branch fitur** (`git checkout -b feature/amazing-thing`)
3. **Commit** perubahan Anda (`git commit -m 'feat: add amazing thing'`)
4. **Push** ke branch Anda (`git push origin feature/amazing-thing`)
5. **Buka Pull Request**

### Panduan Kontribusi

- Semua PR harus lulus **CI pipeline** (lint + test + build)
- Tambahkan **unit tests** untuk fitur baru (target: 70%+ coverage)
- Ikuti gaya kode yang ada (`ruff check` harus clean)
- Perbarui **dokumentasi** jika mengubah API atau perilaku publik
- Periksa **keamanan** — pastikan tidak ada shell injection, path traversal, atau hardcoded secrets

### Current Sprint

Lihat [`docs/SPRINT.md`](docs/SPRINT.md) untuk tugas-tugas yang sedang dikerjakan dan prioritas berikutnya.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**🧠 AIOS — Where AI is the Kernel**

[Built with Claude Code](https://claude.ai/code) · [Report Bug](https://github.com/gacorpoll-ui/aios/issues) · [Request Feature](https://github.com/gacorpoll-ui/aios/issues)

</div>
