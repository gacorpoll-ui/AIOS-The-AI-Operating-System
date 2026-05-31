import os
import glob
from pathlib import Path
from datetime import datetime

def _resolve_safe_path(path_str: str) -> str:
    return os.path.abspath(os.path.expanduser(path_str))

def read_file(path: str, max_lines: int = 500) -> str:
    safe_path = _resolve_safe_path(path)
    if not os.path.exists(safe_path):
        raise FileNotFoundError(f"File not found: {safe_path}")
    if not os.path.isfile(safe_path):
        raise IsADirectoryError(f"Path is a directory: {safe_path}")
        
    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"\n... [File truncated at {max_lines} lines] ...")
                    break
                lines.append(line)
            return "".join(lines)
    except UnicodeDecodeError:
        return "[Binary file or unknown encoding]"

def write_file(path: str, content: str) -> str:
    safe_path = _resolve_safe_path(path)
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"Successfully wrote to {safe_path}"

def list_directory(path: str, show_hidden: bool = False) -> list[dict]:
    safe_path = _resolve_safe_path(path)
    if not os.path.exists(safe_path):
        raise FileNotFoundError(f"Directory not found: {safe_path}")
        
    results = []
    for item in os.scandir(safe_path):
        if not show_hidden and item.name.startswith('.'):
            continue
        stat = item.stat()
        results.append({
            "name": item.name,
            "is_dir": item.is_dir(),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    results.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return results

def search_files(query: str, path: str = ".", file_type: str = None) -> list[str]:
    safe_path = _resolve_safe_path(path)
    if '*' in query or '?' in query:
        search_pattern = os.path.join(safe_path, "**", query)
        matches = glob.glob(search_pattern, recursive=True)
    else:
        matches = []
        for root, _, files in os.walk(safe_path):
            for file in files:
                if query.lower() in file.lower():
                    matches.append(os.path.join(root, file))
    if file_type:
        matches = [m for m in matches if m.endswith(f".{file_type}")]
    return matches[:100]

def get_file_info(path: str) -> dict:
    safe_path = _resolve_safe_path(path)
    if not os.path.exists(safe_path):
        raise FileNotFoundError(f"Path not found: {safe_path}")
    stat = os.stat(safe_path)
    return {
        "path": safe_path,
        "name": os.path.basename(safe_path),
        "size_bytes": stat.st_size,
        "is_dir": os.path.isdir(safe_path),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "permissions": oct(stat.st_mode)[-3:]
    }