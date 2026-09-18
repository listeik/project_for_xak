"""Start the local FastAPI and Vite processes after installing dependencies."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if node is None:
        print("Node.js with npm is required. Install Node.js 22 LTS, then run npm ci in frontend/.")
        return 1
    if not (root / "frontend/node_modules").is_dir():
        print("Install frontend dependencies first: cd frontend && npm ci")
        return 1
    processes: list[subprocess.Popen] = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=root, creationflags=flags,
        ))
        processes.append(subprocess.Popen(
            [node, str(root / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--strictPort"],
            cwd=root / "frontend", creationflags=flags,
        ))
        print("Application: http://localhost:5173 | API documentation: http://127.0.0.1:8000/docs", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        return next((p.returncode for p in processes if p.returncode), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
