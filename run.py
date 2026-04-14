#!/usr/bin/env python3
"""
GitVault — Git-based File Backup Tool
Run this file to start the full application.
"""
import os
import sys
import subprocess

def check_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False

def check_flask():
    try:
        import flask
        return True
    except ImportError:
        return False

if __name__ == "__main__":
    print("""
  ╔══════════════════════════════════════╗
  ║   GitVault — File Backup Tool v2.0  ║
  ╚══════════════════════════════════════╝
""")

    if not check_git():
        print("  ✗ Git not found. Install Git from https://git-scm.com")
        sys.exit(1)
    print("  ✓ Git found")

    if not check_flask():
        print("  Installing Flask...")
        subprocess.run([sys.executable, "-m", "pip", "install", "flask"], check=True)
    print("  ✓ Flask found")

    print("  ✓ Starting server at http://localhost:5000")
    print("  Open your browser → http://localhost:5000\n")

    # Launch Flask app
    backend = os.path.join(os.path.dirname(__file__), "backend", "app.py")
    subprocess.run([sys.executable, backend])
