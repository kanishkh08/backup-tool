"""
GitVault — Backend API Server
Run with: python server.py
Requires: Flask, GitPython
Install:  pip install flask gitpython
"""

import os
import threading
import time
from datetime import datetime, date

from flask import Flask, jsonify, request, send_from_directory
import git

app = Flask(__name__, static_folder=".")

# ── In-memory watch state ─────────────────────────────────────────────────
# { path: { "running": bool, "thread": Thread, "commits": int, "last_check": str, "last_commit": str } }
watch_state: dict[str, dict] = {}


# ── Helpers ───────────────────────────────────────────────────────────────

def get_repo(path: str) -> git.Repo | None:
    """Return a Repo object for path, or None if not a git repo."""
    try:
        return git.Repo(path)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return None


def commit_message(custom: str = "") -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return custom.strip() if custom.strip() else f"AUTO BACKUP — {ts}"


def do_backup(path: str, message: str = "") -> dict:
    """Stage all changes and commit. Returns result dict."""
    repo = get_repo(path)
    if repo is None:
        return {"success": False, "error": "Not a git repository."}

    if not repo.is_dirty(untracked_files=True):
        return {"success": False, "message": "Nothing to commit — working tree is clean."}

    repo.git.add(A=True)
    msg = commit_message(message)
    commit = repo.index.commit(msg)
    return {
        "success": True,
        "committed_message": msg,
        "hash": commit.hexsha,
        "output": f"[{commit.hexsha[:7]}] {msg}",
    }


def watch_loop(path: str, interval: int):
    """Background thread: check for changes and commit at each interval."""
    state = watch_state[path]
    while state.get("running"):
        state["last_check"] = datetime.now().strftime("%H:%M:%S")
        result = do_backup(path)
        if result.get("success"):
            state["commits"] = state.get("commits", 0) + 1
            state["last_commit"] = datetime.now().strftime("%H:%M:%S")
        time.sleep(interval)


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/init", methods=["POST"])
def api_init():
    """Initialise (or verify) a git repo at the given path."""
    data = request.get_json()
    path = data.get("path", "").strip()

    if not os.path.isdir(path):
        return jsonify({"error": f"Directory not found: {path}"}), 400

    repo = get_repo(path)
    if repo is None:
        repo = git.Repo.init(path)
        return jsonify({"success": True, "repo": "initialized", "path": path})

    return jsonify({"success": True, "repo": "existing", "path": path})


@app.route("/api/backup", methods=["POST"])
def api_backup():
    data    = request.get_json()
    path    = data.get("path", "").strip()
    message = data.get("message", "")

    if not path:
        return jsonify({"error": "No path provided."}), 400

    result = do_backup(path, message)
    return jsonify(result)


@app.route("/api/stats", methods=["POST"])
def api_stats():
    data = request.get_json()
    path = data.get("path", "").strip()
    repo = get_repo(path)

    if repo is None:
        return jsonify({"error": "Not a git repository."})

    try:
        commits = list(repo.iter_commits())
    except git.GitCommandError:
        commits = []

    today_str  = date.today().isoformat()
    today_count = sum(
        1 for c in commits
        if datetime.fromtimestamp(c.committed_date).date().isoformat() == today_str
    )

    last_backup  = "—"
    last_message = "No backups yet"
    if commits:
        last_backup  = datetime.fromtimestamp(commits[0].committed_date).strftime("%H:%M:%S")
        last_message = commits[0].message.strip()[:60]

    return jsonify({
        "total_backups": len(commits),
        "today_backups": today_count,
        "last_backup":   last_backup,
        "last_message":  last_message,
    })


@app.route("/api/log", methods=["POST"])
def api_log():
    data  = request.get_json()
    path  = data.get("path", "").strip()
    count = int(data.get("count", 20))
    repo  = get_repo(path)

    if repo is None:
        return jsonify({"commits": []})

    try:
        raw = list(repo.iter_commits(max_count=count))
    except git.GitCommandError:
        raw = []

    commits = [
        {
            "hash":    c.hexsha,
            "short":   c.hexsha[:7],
            "message": c.message.strip()[:80],
            "date":    datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
            "author":  str(c.author),
        }
        for c in raw
    ]
    return jsonify({"commits": commits})


@app.route("/api/status", methods=["POST"])
def api_status():
    data = request.get_json()
    path = data.get("path", "").strip()
    repo = get_repo(path)

    if repo is None:
        return jsonify({"error": "Not a git repository."})

    files   = []
    added   = 0
    modified = 0
    deleted = 0

    # Staged / tracked changes
    if repo.head.is_valid():
        diff = repo.index.diff(None)
        for d in diff:
            status = d.change_type  # 'M', 'A', 'D', 'R', etc.
            files.append({"file": d.a_path, "status": status})
            if status == "M":
                modified += 1
            elif status == "A":
                added += 1
            elif status == "D":
                deleted += 1

    # Untracked files
    for f in repo.untracked_files:
        files.append({"file": f, "status": "??"})
        added += 1

    clean = not repo.is_dirty(untracked_files=True)
    return jsonify({
        "is_repo":  True,
        "clean":    clean,
        "added":    added,
        "modified": modified,
        "deleted":  deleted,
        "total":    len(files),
        "files":    files,
    })


@app.route("/api/restore", methods=["POST"])
def api_restore():
    data   = request.get_json()
    path   = data.get("path", "").strip()
    commit = data.get("commit", "").strip()
    repo   = get_repo(path)

    if repo is None:
        return jsonify({"error": "Not a git repository."})
    if not commit:
        return jsonify({"error": "No commit hash provided."})

    try:
        repo.git.checkout(commit, "--", ".")
        return jsonify({"success": True, "output": f"Restored to {commit[:7]}"})
    except git.GitCommandError as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/restore/latest", methods=["POST"])
def api_restore_latest():
    data = request.get_json()
    path = data.get("path", "").strip()
    repo = get_repo(path)

    if repo is None:
        return jsonify({"error": "Not a git repository."})

    try:
        repo.git.checkout("HEAD", "--", ".")
        return jsonify({"success": True})
    except git.GitCommandError as e:
        return jsonify({"success": False, "error": str(e)})


# ── Watch endpoints ───────────────────────────────────────────────────────

@app.route("/api/watch/start", methods=["POST"])
def api_watch_start():
    data     = request.get_json()
    path     = data.get("path", "").strip()
    interval = int(data.get("interval", 60))

    if not path:
        return jsonify({"error": "No path provided."})
    if get_repo(path) is None:
        return jsonify({"error": "Not a git repository."})

    # Stop existing watcher if present
    if path in watch_state and watch_state[path].get("running"):
        watch_state[path]["running"] = False
        watch_state[path]["thread"].join(timeout=5)

    watch_state[path] = {
        "running":     True,
        "commits":     0,
        "last_check":  None,
        "last_commit": None,
    }
    t = threading.Thread(target=watch_loop, args=(path, interval), daemon=True)
    watch_state[path]["thread"] = t
    t.start()

    return jsonify({"success": True, "message": f"Watching {path} every {interval}s"})


@app.route("/api/watch/stop", methods=["POST"])
def api_watch_stop():
    data = request.get_json()
    path = data.get("path", "").strip()

    if path in watch_state:
        watch_state[path]["running"] = False

    return jsonify({"success": True})


@app.route("/api/watch/status", methods=["POST"])
def api_watch_status():
    data  = request.get_json()
    path  = data.get("path", "").strip()
    state = watch_state.get(path, {})

    return jsonify({
        "running":     state.get("running", False),
        "commits":     state.get("commits", 0),
        "last_check":  state.get("last_check"),
        "last_commit": state.get("last_commit"),
    })


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("GitVault backend running at http://localhost:5000")
    app.run(debug=True, port=5000)