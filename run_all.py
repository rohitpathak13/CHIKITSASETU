"""
CHIKITSASETU - Unified Project Runner
Launches both the Flask Clinical Web Portal and FastAPI REST & ML Service.
Usage:
    python run_all.py
"""
import os
import sys
import subprocess
import time
import signal

def print_banner():
    print("=" * 65)
    print("       🏥  CHIKITSASETU - SMART HOSPITAL MANAGEMENT SYSTEM       ")
    print("=" * 65)
    print("  ► Flask Clinical Portal:   http://127.0.0.1:5000")
    print("  ► FastAPI REST & ML Docs:  http://127.0.0.1:8000/docs")
    print("  ► ReDoc API Docs:          http://127.0.0.1:8000/redoc")
    print("-" * 65)
    print("  ► Demo Admin Login:        admin@chikitsasetu.ai  /  Password123!")
    print("  ► Demo Doctor Login:       dr.sharma@chikitsasetu.ai / Password123!")
    print("  ► Demo Patient Login:      patient.john@chikitsasetu.ai / Password123!")
    print("=" * 65)
    print("  Press Ctrl+C at any time to stop both servers.")
    print("=" * 65 + "\n")

def main():
    print_banner()
    root_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable

    # Start FastAPI
    print("[*] Starting FastAPI REST & ML Inference Service on port 8000...")
    fastapi_proc = subprocess.Popen(
        [python_exe, os.path.join(root_dir, "run_fastapi.py")],
        cwd=root_dir
    )

    # Short delay to let FastAPI initialize
    time.sleep(1.5)

    # Start Flask
    print("[*] Starting Flask Clinical Web Portal on port 5000...")
    flask_proc = subprocess.Popen(
        [python_exe, os.path.join(root_dir, "run_flask.py")],
        cwd=root_dir
    )

    print("\n[+] Both services are running!\n")

    def handle_shutdown(signum, frame):
        print("\n[*] Gracefully stopping CHIKITSASETU services...")
        try:
            flask_proc.terminate()
        except Exception:
            pass
        try:
            fastapi_proc.terminate()
        except Exception:
            pass
        print("[+] Servers stopped successfully.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handle_shutdown)

    try:
        while True:
            # Check if any process died unexpectedly
            if flask_proc.poll() is not None:
                print(f"[!] Flask server exited with code {flask_proc.returncode}")
                break
            if fastapi_proc.poll() is not None:
                print(f"[!] FastAPI server exited with code {fastapi_proc.returncode}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        handle_shutdown(None, None)

if __name__ == "__main__":
    main()
