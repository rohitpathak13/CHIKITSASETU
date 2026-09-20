"""
MediCare AI - Container Verification Test Script
Tests running Docker containers: Flask, FastAPI, PostgreSQL, and OpenAPI Docs.
"""
import sys
import json
import re
import urllib.request
import urllib.parse
import http.cookiejar

def test_fastapi():
    print("[1/4] Testing FastAPI service at http://127.0.0.1:8080/ ...")
    resp = urllib.request.urlopen("http://127.0.0.1:8080/")
    assert resp.status == 200, f"Expected 200, got {resp.status}"
    data = json.loads(resp.read().decode("utf-8"))
    assert data.get("status") == "operational", f"Unexpected response: {data}"
    print("  -> PASSED: FastAPI is operational (version: {})".format(data.get("version")))

def test_api_docs():
    print("[2/4] Testing FastAPI Documentation at http://127.0.0.1:8080/docs and /openapi.json ...")
    docs_resp = urllib.request.urlopen("http://127.0.0.1:8080/docs")
    assert docs_resp.status == 200, f"Swagger docs returned {docs_resp.status}"
    
    redoc_resp = urllib.request.urlopen("http://127.0.0.1:8080/redoc")
    assert redoc_resp.status == 200, f"ReDoc returned {redoc_resp.status}"

    openapi_resp = urllib.request.urlopen("http://127.0.0.1:8080/openapi.json")
    assert openapi_resp.status == 200, f"OpenAPI spec returned {openapi_resp.status}"
    openapi_data = json.loads(openapi_resp.read().decode("utf-8"))
    endpoint_count = len(openapi_data.get("paths", {}))
    print(f"  -> PASSED: Swagger UI, ReDoc, and OpenAPI spec verified ({endpoint_count} endpoints documented)")

def test_flask_portal():
    print("[3/4] Testing Flask Web Portal at http://127.0.0.1:5050/login ...")
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # Fetch login page
    resp = opener.open("http://127.0.0.1:5050/login")
    assert resp.status == 200, f"Login page returned {resp.status}"
    html = resp.read().decode("utf-8")
    assert "Sign In - MediCare AI" in html, "Missing login page title"

    # Extract CSRF token
    token_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    token = token_match.group(1) if token_match else ""

    # Login as admin
    post_data = urllib.parse.urlencode({
        "email": "admin@medicare.ai",
        "password": "Password123!",
        "csrf_token": token
    }).encode("utf-8")

    login_resp = opener.open("http://127.0.0.1:5050/login", data=post_data)
    login_html = login_resp.read().decode("utf-8")
    assert login_resp.status == 200, f"Admin portal returned {login_resp.status}"
    assert "System Overview" in login_html or "Administration" in login_html, "Failed to reach admin dashboard"
    print("  -> PASSED: Flask portal login successful. Authenticated as Admin (admin@medicare.ai)")

def test_postgres_direct():
    print("[4/4] Testing PostgreSQL Direct Connection via psycopg2 at localhost:5433 ...")
    import psycopg2
    conn = psycopg2.connect(
        dbname="medicare_ai",
        user="postgres",
        password="postgres_secure_2026",
        host="localhost",
        port=5433
    )
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM users;")
    user_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM roles;")
    role_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM beds;")
    bed_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"  -> PASSED: Connected to PostgreSQL successfully ({user_count} users, {role_count} roles, {bed_count} beds)")

if __name__ == "__main__":
    print("==================================================")
    print(" MediCare AI - Container Verification Test Suite  ")
    print("==================================================")
    try:
        test_fastapi()
        test_api_docs()
        test_flask_portal()
        test_postgres_direct()
        print("==================================================")
        print(" ALL 4 CONTAINER SERVICES VERIFIED SUCCESSFULLY!  ")
        print("==================================================")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)
