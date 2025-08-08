# Moniters the deployed Application

from flask import Flask
import threading
import requests
import time
import subprocess
import os
import json
import sys
 
app = Flask(__name__)
 
# === CONFIG ===
CHECK_INTERVAL = 5  # seconds
FAILOVER_SCRIPT = "./automation.sh"
 
# === State Tracking ===
APP_NAME = None
APP_URL = None
has_triggered_failover = False
 
 
def is_cf_logged_in():
    try:
        result = subprocess.run(["cf", "target"], capture_output=True, text=True)
        return "Not logged in." not in result.stdout
    except Exception:
        return False
 
 
def run_cf_login():
    try:
        print("🔐 Opening interactive CF login...")
        subprocess.run(["cf", "login"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ CF login failed: {e}")
        return False
 
 
def get_app_url(app_name):
    try:
        print(f"🔍 Fetching route for app: {app_name}")
        app_guid = subprocess.check_output(
            ["cf", "app", app_name, "--guid"], text=True
        ).strip()
 
        route_data = subprocess.check_output(
            ["cf", "curl", f"/v3/apps/{app_guid}/routes"], text=True
        )
 
        route_json = json.loads(route_data)
        url_path = route_json["resources"][0]["url"]
        full_url = f"https://{url_path}"
        print(f"🌐 Resolved app URL: {full_url}")
        return full_url
 
    except Exception as e:
        print(f"❌ Failed to retrieve app URL: {e}")
        return None
 
 
def health_check_loop():
    global has_triggered_failover, APP_URL
 
    while True:
        if not APP_URL:
            print("⚠️ Skipping health check — app URL not available.")
        else:
            try:
                print(f"🔍 Checking health of {APP_URL} ...")
                response = requests.get(APP_URL, timeout=10)
                if response.status_code == 200:
                    print("✅ App is healthy.")
                    has_triggered_failover = False
                else:
                    print(f"⚠️ Unexpected status: {response.status_code}")
                    trigger_failover()
            except requests.RequestException as e:
                print(f"❌ App check failed: {e}")
                trigger_failover()
 
        time.sleep(CHECK_INTERVAL)
 
 
def trigger_failover():
    global has_triggered_failover, APP_URL
 
    if has_triggered_failover:
        print("⏳ Failover already triggered. Waiting for recovery...")
        return
 
    print("🚨 App is DOWN! Triggering failover...")
    try:
        result = subprocess.run(["bash", FAILOVER_SCRIPT])
        print("📜 Failover script output:")
        print(result.stdout)
 
        if result.returncode != 0:
            print("❌ Failover failed:", result.stderr)
        else:
            print("✅ Failover completed.")
            has_triggered_failover = True
 
            # ✅ Update the app URL *only after* successful failover
            print("🔄 Resolving new app URL after failover...")
            new_url = get_app_url(APP_NAME)
            if new_url:
                APP_URL = new_url
                print(f"✅ Updated APP_URL to: {APP_URL}")
            else:
                print("⚠️ Could not resolve new app URL after failover.")
 
    except Exception as e:
        print(f"⚠️ Error running failover script: {e}")
 
 
 
@app.route("/health-monitor")
def monitor():
    return "Health check service is running", 200
 
 
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Usage: python health_check.py <APP_NAME>")
        sys.exit(1)

    APP_NAME = sys.argv[1]

    if not is_cf_logged_in():
        print("⚠️ You are not logged in to Cloud Foundry.")
        choice = input("👉 Do you want to log in now? (y/n): ").strip().lower()
        if choice == "y":
            if not run_cf_login():
                print("❌ Exiting due to failed login.")
                sys.exit(1)
        else:
            print("❌ Login required to fetch app URL. Exiting.")
            sys.exit(1)

    print(f"🚀 Starting Flask health check service for app: {APP_NAME}")

    APP_URL = get_app_url(APP_NAME)
    if not APP_URL:
        print("⚠️ App URL not found. Assuming app is already down.")
        trigger_failover()
        # Reattempt to fetch new app URL after failover
        APP_URL = get_app_url(APP_NAME)
        if not APP_URL:
            print("⚠️ Still unable to resolve APP_URL after failover. Will retry in background.")

    thread = threading.Thread(target=health_check_loop)
    thread.daemon = True
    thread.start()

    app.run(host="0.0.0.0", port=5000)