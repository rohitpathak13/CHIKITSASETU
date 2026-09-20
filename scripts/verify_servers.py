import subprocess
import time
import sys
import requests

def test_servers():
    print("==================================================")
    print(" MediCare AI - Multi-Server Startup Verification  ")
    print("==================================================")

    # 1. Start Flask process
    print("[*] Launching Flask Web Application (run_flask.py)...")
    flask_proc = subprocess.Popen([sys.executable, "run_flask.py"])

    # 2. Start FastAPI process
    print("[*] Launching FastAPI REST Engine (run_fastapi.py)...")
    fastapi_proc = subprocess.Popen([sys.executable, "run_fastapi.py"])

    flask_ok = False
    fastapi_ok = False
    fastapi_docs_ok = False

    try:
        # Polling loop up to 10 seconds for Flask
        for attempt in range(10):
            try:
                r = requests.get("http://127.0.0.1:5000/login", timeout=2)
                if r.status_code == 200:
                    print(f"[+] Flask HTTP Status: {r.status_code} (Login page rendered: {len(r.content)} bytes)")
                    flask_ok = True
                    break
            except Exception:
                time.sleep(1)

        # Polling loop up to 10 seconds for FastAPI
        for attempt in range(10):
            try:
                r = requests.get("http://127.0.0.1:8000/", timeout=2)
                if r.status_code == 200:
                    print(f"[+] FastAPI HTTP Status: {r.status_code} (Root payload: {r.json()})")
                    fastapi_ok = True
                    break
            except Exception:
                time.sleep(1)

        # Check FastAPI Swagger Docs
        try:
            r = requests.get("http://127.0.0.1:8000/docs", timeout=2)
            if r.status_code == 200:
                print(f"[+] FastAPI Swagger Docs Status: {r.status_code} (OpenAPI UI active)")
                fastapi_docs_ok = True
        except Exception as e:
            print(f"[-] FastAPI docs check failed: {e}")

    finally:
        print("[*] Terminating test background server processes...")
        flask_proc.terminate()
        fastapi_proc.terminate()
        try:
            flask_proc.wait(timeout=3)
            fastapi_proc.wait(timeout=3)
        except Exception:
            flask_proc.kill()
            fastapi_proc.kill()

    print("==================================================")
    if flask_ok and fastapi_ok and fastapi_docs_ok:
        print(" [+] SUCCESS: Both Flask & FastAPI started and verified!")
        print("==================================================")
        sys.exit(0)
    else:
        print(" [-] ERROR: One or more server checks failed.")
        print(f"     Flask OK: {flask_ok}, FastAPI OK: {fastapi_ok}, Docs OK: {fastapi_docs_ok}")
        print("==================================================")
        sys.exit(1)

if __name__ == "__main__":
    test_servers()
