"""
run.py — Startup script for Curious History.
Automatically creates a free HTTPS tunnel (serveo.net) so Google Sign-In
works on mobile without any account or installation needed.

Run with:  python3 run.py
"""

import os
import sys
import re
import subprocess
import threading

os.chdir(os.path.dirname(os.path.abspath(__file__)))

port = int(os.getenv("PORT", "5001"))

# ── Start a free HTTPS tunnel via serveo.net (SSH — built into macOS) ─────────
# This gives a public HTTPS URL that works for Google Sign-In on any device.
https_url = None

def start_tunnel():
    global https_url
    try:
        proc = subprocess.Popen(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-o", "ExitOnForwardFailure=yes",
                "-R", f"80:localhost:{port}",
                "serveo.net",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Read lines until we see the public HTTPS URL
        for line in proc.stdout:
            match = re.search(r"https://[^\s]+", line)
            if match:
                https_url = match.group(0).rstrip(".")
                break
        proc.wait()
    except Exception as exc:
        pass   # tunnel failed; app still runs on local IP

tunnel_thread = threading.Thread(target=start_tunnel, daemon=True)
tunnel_thread.start()
tunnel_thread.join(timeout=8)   # wait up to 8 s for the URL to appear

# ── Print access URLs ──────────────────────────────────────────────────────────
print("\n" + "=" * 62)
print("  Curious History is running!\n")
print(f"  This computer  →  http://localhost:{port}")

if https_url:
    print(f"  Mobile / any   →  {https_url}")
    print()
    print("  ⚠  One-time Google Cloud Console setup (for Sign-In):")
    print(f"     1. Go to console.cloud.google.com")
    print(f"     2. APIs & Services → Credentials → your OAuth Client → Edit")
    print(f"     3. Add this to Authorized JavaScript Origins:")
    print(f"        {https_url}")
    print(f"     4. Save, wait ~30 s, then try Sign-In on your phone")
    print()
    print("  NOTE: This HTTPS URL changes each server restart.")
    print("  For a permanent URL, sign up free at ngrok.com and run:")
    print("     ngrok config add-authtoken YOUR_TOKEN")
else:
    print(f"  Mobile         →  http://192.168.1.16:{port}")
    print()
    print("  ⚠  Tunnel could not start — Google Sign-In may not work on mobile.")
    print("  Make sure your Mac allows SSH outbound connections.")

print("=" * 62 + "\n")

# ── Import and start Flask ─────────────────────────────────────────────────────
from app import app
from config import Config

app.run(debug=Config.DEBUG, host="0.0.0.0", port=port, use_reloader=False)
