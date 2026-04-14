# GitVault — Git-based File Backup Tool (Full Stack)
<!-- Frontend developed by Kanishk patel -->

A complete **frontend + backend** file backup application that uses Git as a versioning engine to automate backups of any local directory.

---

## Features

| Feature | Description |
|---|---|
| Dashboard | Live stats — total backups, today's count, last backup time |
| Manual Backup | Single on-demand commit with custom message |
| Auto Watch | Background watcher that auto-commits on any file change |
| Backup History | Full log of all backup commits with hashes & timestamps |
| Restore | Roll back any directory to any previous backup state |
| File Status | Live Git status showing modified / added / deleted files |

---

## Setup & Run

### Requirements
- Python 3.10+
- Git (installed and in PATH)
- Flask (`pip install flask`)

### Run the App

```bash
python run.py
```

Then open your browser at: **http://localhost:5000**

---

## How to Use

1. **Enter a directory path** in the top bar and click **LOAD**
2. **Dashboard** shows your backup stats instantly
3. **Manual Backup** — go to Manual Backup → click "Create Backup"
4. **Auto Watch** — go to Auto Watch → set interval → click "Start Watching"
5. **History** — view all past backups with timestamps
6. **Restore** — click any hash in History, confirm, and restore

---

## Project Structure

```
git-backup-fullstack/
├── run.py                    ← Start the app from here
├── backend/
│   └── app.py                ← Flask API (all Git operations)
└── frontend/
    └── templates/
        └── index.html        ← Full dashboard UI
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/init` | POST | Initialize Git repo in directory |
| `/api/backup` | POST | Create a manual backup commit |
| `/api/watch/start` | POST | Start auto-watch mode |
| `/api/watch/stop` | POST | Stop auto-watch mode |
| `/api/watch/status` | POST | Check watch status |
| `/api/log` | POST | Get backup history |
| `/api/status` | POST | Get Git status of directory |
| `/api/stats` | POST | Get backup statistics |
| `/api/restore` | POST | Restore to a specific commit |
| `/api/restore/latest` | POST | Return to latest backup |

---

## Team

- Member 1 (Lead) — Backend API (`app.py`)
- Member 2 — Frontend Dashboard (`index.html`)
- Member 3 — Integration & README (`run.py`)
