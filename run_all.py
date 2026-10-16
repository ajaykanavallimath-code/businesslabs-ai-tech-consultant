"""
Single-Command Startup Orchestrator for the BusinessLabs AI Tech Consultant Capstone.
Manages concurrent execution of:
  - Task 1: Knowledge Brain (FastAPI @ port 8000)
  - Task 2: Inbox Agent (Express/TypeScript @ port 3000)
  - Task 3: Meeting to Scope (FastAPI @ port 8001)

Usage:
  python run_all.py              # Launch all 3 services together
  python run_all.py --verify     # Launch, probe health endpoints, report verification, and exit
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

ROOT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable

# Locate Task 1 virtual environment python if running from global python
KB_VENV_PY = ROOT_DIR / "knowledge-brain" / ".venv" / "Scripts" / "python.exe"
if KB_VENV_PY.exists():
    PYTHON_EXE = str(KB_VENV_PY)


def probe_url(url: str, timeout: float = 2.0) -> bool:
    """Check if HTTP endpoint is responding."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def start_task1():
    """Start Task 1: Knowledge Brain."""
    cwd = ROOT_DIR / "knowledge-brain"
    cmd = [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "src.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--log-level",
        "info",
    ]
    return subprocess.Popen(cmd, cwd=str(cwd))


def start_task2():
    """Start Task 2: Inbox Agent."""
    cwd = ROOT_DIR / "task2-inbox-agent"
    cmd = "npm start"
    return subprocess.Popen(cmd, cwd=str(cwd), shell=True)


def start_task3():
    """Start Task 3: Meeting to Scope."""
    cwd = ROOT_DIR / "task3-meeting-scope"
    cmd = [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "src.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
        "--log-level",
        "info",
    ]
    return subprocess.Popen(cmd, cwd=str(cwd))


def terminate_processes(procs):
    """Cleanly shut down all child processes."""
    print("\n[*] Shutting down services...")
    for name, proc in procs:
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.terminate()
            print(f"  [+] Stopped {name}")
        except Exception as e:
            pass


def main():
    parser = argparse.ArgumentParser(description="Start all BusinessLabs capstone services")
    parser.add_argument("--verify", action="store_true", help="Start, probe health, and exit")
    args = parser.parse_args()

    print("=" * 70)
    print(" BusinessLabs AI Tech Consultant — Integrated Platform Startup")
    print("=" * 70)
    print(f"Root Directory: {ROOT_DIR}")
    print(f"Python Runtime: {PYTHON_EXE}")

    procs = []
    try:
        print("\n[1/3] Launching Task 1: Knowledge Brain on http://127.0.0.1:8000 ...")
        p1 = start_task1()
        procs.append(("Task 1 Knowledge Brain", p1))

        print("[2/3] Launching Task 2: Inbox Agent on http://127.0.0.1:3000 ...")
        p2 = start_task2()
        procs.append(("Task 2 Inbox Agent", p2))

        print("[3/3] Launching Task 3: Meeting to Scope on http://127.0.0.1:8001 ...")
        p3 = start_task3()
        procs.append(("Task 3 Meeting to Scope", p3))

        print("\n[*] Waiting for services to initialize...")
        endpoints = [
            ("Task 1 Knowledge Brain", "http://127.0.0.1:8000/api/v1/health"),
            ("Task 2 Inbox Agent", "http://127.0.0.1:3000/api/v1/inbox/health"),
            ("Task 3 Meeting to Scope", "http://127.0.0.1:8001/api/v1/health"),
        ]

        healthy = {}
        for attempt in range(1, 15):
            time.sleep(1.0)
            for name, url in endpoints:
                if name not in healthy and probe_url(url):
                    healthy[name] = True
                    print(f"  [OK] {name} is HEALTHY ({url})")
            if len(healthy) == len(endpoints):
                break

        print("\n" + "=" * 70)
        print(" Platform Services Status:")
        print("=" * 70)
        for name, url in endpoints:
            status_str = "ACTIVE & HEALTHY" if name in healthy else "INITIALIZING / PENDING"
            print(f"  - {name:25s}: {status_str} -> {url}")
        print("=" * 70)
        print("  [*] Unified Frontend Dashboard : READY -> http://127.0.0.1:3000")
        print("=" * 70)

        if args.verify:
            all_ok = len(healthy) == len(endpoints)
            print(f"\nVerification Result: {'PASSED' if all_ok else 'PARTIAL'}")
            return 0 if all_ok else 1

        print("\nAll services running. Press Ctrl+C to terminate all services.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nReceived interrupt signal.")
    finally:
        terminate_processes(procs)


if __name__ == "__main__":
    sys.exit(main() or 0)
