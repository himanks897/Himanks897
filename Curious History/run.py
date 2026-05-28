"""
run.py — Simple startup script for Curious History.
Run this with:  python3 run.py
Then open:      http://localhost:5001
"""

import sys
import subprocess
import os

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Check Python packages are installed
required = ["flask", "requests", "google.genai", "dotenv"]
missing = []
for pkg in required:
    try:
        __import__(pkg.replace(".", "/").replace("/", "."))
    except ImportError:
        missing.append(pkg)

if missing:
    print(f"Installing missing packages…")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "flask", "flask-cors", "python-dotenv",
                           "requests", "google-genai", "cachetools"])

# Now start the app
from app import app
from config import Config

port = int(os.getenv("PORT", "5001"))
print(f"\n{'='*50}")
print(f"  Curious History is starting…")
print(f"  Open this URL in your browser:")
print(f"\n  ➜  http://localhost:{port}")
print(f"\n{'='*50}\n")
app.run(debug=Config.DEBUG, host="0.0.0.0", port=port, use_reloader=True)
