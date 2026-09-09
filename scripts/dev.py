"""Run both development servers; stop both when either exits."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        print("Node.js 24+ and npm are required.", file=sys.stderr)
        return 1
    if not (ROOT / "frontend" / "node_modules").is_dir():
        print("Run npm --prefix frontend ci first.", file=sys.stderr)
        return 1
    if not (ROOT / ".env").is_file():
        print("Copy .env.example to .env and configure the database first.", file=sys.stderr)
        return 1
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    children: list[subprocess.Popen] = []
    try:
        children.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--reload",
             "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT / "backend", **options,
        ))
        children.append(subprocess.Popen(
            [npm, "run", "dev"], cwd=ROOT / "frontend", **options,
        ))
        print("Frontend: http://localhost:5173 | API: http://localhost:8000/docs")
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        return next((child.returncode for child in children if child.returncode is not None), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
