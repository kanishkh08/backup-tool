"""
Git-based File Backup Tool — Flask Backend API
Serves the frontend and exposes REST endpoints for all Git backup operations.
"""

import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

# ── App setup ─────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "frontend" / "static"
TMPL_DIR   = BASE_DIR / "frontend" / "templates"

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TMPL_DIR),
)

# In-memory watch-thread registry  {directory: threading.Thread}
_watch_threads: dict[str, threading.Thread] = {}
_watch_stop:    dict[str, threading.Event]  = {}
_watch_status:  dict[str, dict]             = {}   # live status per directory

# ── Git helpers ───────────────────────────────────────────────────────────────

def _git(args: list, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True
    )

def _is_repo(path: str) -> bool:
    return _git(["rev-parse", "--is-inside-work-tree"], path).returncode == 0

def _init(path: str) -> str:
    if not _is_repo(path):
        _git(["init"], path)
        return "initialized"
    return "existing"

def _has_changes(path: str) -> bool:
    return bool(_git(["status", "--porcelain"], path).stdout.strip())

def _stage_commit(path: str, message: str) -> dict:
    _git(["add", "-A"], path)
    result = _git(["commit", "-m", message], path)
    return {
        "success": result.returncode == 0,
        "output": result.stdout.strip() or result.stderr.strip(),
    }

def _get_log(path: str, n: int = 20) -> list[dict]:
    result = _git(
        ["log", f"-{n}", "--pretty=format:%H|%h|%s|%ad|%an", "--date=format:%d %b %Y, %I:%M %p"],
        path,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    entries = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("|")
        if len(parts) >= 5:
            entries.append({
                "hash":    parts[0],
                "short":   parts[1],
                "message": parts[2],
                "date":    parts[3],
                "author":  parts[4],
            })
    return entries

def _get_status(path: str) -> dict:
    r = _git(["status", "--porcelain"], path)
    lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
    added    = sum(1 for l in lines if l.startswith("A") or l.startswith("?"))
    modified = sum(1 for l in lines if l.startswith(" M") or l.startswith("M"))
    deleted  = sum(1 for l in lines if l.startswith(" D") or l.startswith("D"))
    return {
        "is_repo":  _is_repo(path),
        "clean":    len(lines) == 0,
        "added":    added,
        "modified": modified,
        "deleted":  deleted,
        "total":    len(lines),
        "files":    [{"status": l[:2].strip(), "file": l[3:]} for l in lines[:30]],
    }

def _get_stats(path: str) -> dict:
    log   = _get_log(path, 100)
    today = datetime.now().strftime("%d %b %Y")
    today_count = sum(1 for e in log if today in e.get("date", ""))
    result = _git(["rev-list", "--count", "HEAD"], path)
    total  = int(result.stdout.strip()) if result.returncode == 0 else 0
    return {
        "total_backups": total,
        "today_backups": today_count,
        "last_backup":   log[0]["date"] if log else "Never",
        "last_message":  log[0]["message"] if log else "—",
    }

# ── Watch thread ──────────────────────────────────────────────────────────────

def _watch_loop(path: str, interval: int, stop_event: threading.Event):
    _watch_status[path] = {
        "running": True, "last_check": "", "last_commit": "", "commits": 0
    }
    while not stop_event.is_set():
        ts = datetime.now().strftime("%H:%M:%S")
        _watch_status[path]["last_check"] = ts
        if _has_changes(path):
            msg = f"[AUTO BACKUP] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            res = _stage_commit(path, msg)
            if res["success"]:
                _watch_status[path]["last_commit"] = ts
                _watch_status[path]["commits"] = _watch_status[path].get("commits", 0) + 1
        stop_event.wait(interval)
    _watch_status[path]["running"] = False

# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(TMPL_DIR), "index.html")

@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# -- Directory: init / status / stats
@app.route("/api/init", methods=["POST"])
def api_init():
    data = request.json or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": f"Directory not found: {path}"}), 400
    repo_status = _init(path)
    return jsonify({"success": True, "path": path, "repo": repo_status})

@app.route("/api/status", methods=["POST"])
def api_status():
    data = request.json or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    if not _is_repo(path):
        _init(path)
    return jsonify(_get_status(path))

@app.route("/api/stats", methods=["POST"])
def api_stats():
    data = request.json or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    if not _is_repo(path):
        return jsonify({"total_backups": 0, "today_backups": 0, "last_backup": "Never", "last_message": "—"})
    return jsonify(_get_stats(path))

# -- Backup: manual single commit
@app.route("/api/backup", methods=["POST"])
def api_backup():
    data    = request.json or {}
    path    = data.get("path", "").strip()
    message = data.get("message", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    _init(path)
    if not _has_changes(path):
        return jsonify({"success": False, "message": "No changes detected. Nothing to backup."})
    msg = message or f"[MANUAL BACKUP] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    result = _stage_commit(path, msg)
    return jsonify({**result, "committed_message": msg})

# -- Watch: start / stop / status
@app.route("/api/watch/start", methods=["POST"])
def api_watch_start():
    data     = request.json or {}
    path     = data.get("path", "").strip()
    interval = int(data.get("interval", 60))
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    if path in _watch_threads and _watch_threads[path].is_alive():
        return jsonify({"success": False, "message": "Watch already running for this directory."})
    _init(path)
    stop_evt = threading.Event()
    t = threading.Thread(target=_watch_loop, args=(path, interval, stop_evt), daemon=True)
    _watch_threads[path] = t
    _watch_stop[path]    = stop_evt
    t.start()
    return jsonify({"success": True, "message": f"Auto-watch started (every {interval}s)"})

@app.route("/api/watch/stop", methods=["POST"])
def api_watch_stop():
    data = request.json or {}
    path = data.get("path", "").strip()
    if path in _watch_stop:
        _watch_stop[path].set()
        return jsonify({"success": True, "message": "Watch stopped."})
    return jsonify({"success": False, "message": "No watch running for this directory."})

@app.route("/api/watch/status", methods=["POST"])
def api_watch_status():
    data = request.json or {}
    path = data.get("path", "").strip()
    running = path in _watch_threads and _watch_threads[path].is_alive()
    info    = _watch_status.get(path, {})
    return jsonify({"running": running, **info})

# -- Log: backup history
@app.route("/api/log", methods=["POST"])
def api_log():
    data = request.json or {}
    path = data.get("path", "").strip()
    n    = int(data.get("count", 20))
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    if not _is_repo(path):
        return jsonify({"commits": []})
    return jsonify({"commits": _get_log(path, n)})

# -- Restore: checkout a commit
@app.route("/api/restore", methods=["POST"])
def api_restore():
    data   = request.json or {}
    path   = data.get("path", "").strip()
    commit = data.get("commit", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    if not commit:
        return jsonify({"error": "Commit hash required"}), 400
    result = _git(["checkout", commit], path)
    return jsonify({
        "success": result.returncode == 0,
        "output":  result.stdout.strip() or result.stderr.strip(),
    })

@app.route("/api/restore/latest", methods=["POST"])
def api_restore_latest():
    data = request.json or {}
    path = data.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Directory not found"}), 400
    result = _git(["checkout", "HEAD"], path)
    result2 = _git(["checkout", "main"], path)
    if result2.returncode != 0:
        _git(["checkout", "master"], path)
    return jsonify({"success": True, "message": "Restored to latest backup."})

if __name__ == "__main__":
    print("\n  Git Backup Tool — Backend Running")
    print("  Open: http://localhost:5000\n")
    app.run(debug=True, port=5000, threaded=True)
