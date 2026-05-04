from dotenv import load_dotenv

load_dotenv()

from src.interfaces.flask_api import launch_flask
import requests
import time
import threading
from os import getenv


def _getenv_int(name: str, default: int) -> int:
    value = getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"⚠️  Invalid value for {name}: {value!r}. Using default {default}.")
        return default

    
LLM_BACKEND = getenv("LLM_BACKEND", "ollama")
LLM_MODEL = getenv("LLM_MODEL", "ifenpay-llm-v1")
AGENT_MODE = getenv("AGENT_MODE", "assistant")
HOST = getenv("HOST", "0.0.0.0")
PORT = getenv("PORT", "7560")
LLM_HOST = getenv("LLM_HOST", "http://0.0.0.0:11434")
LLM_PRELOAD_MODEL = getenv("LLM_PRELOAD_MODEL", "false").lower() == "true"


print(f"🚀 Starting Nano Agent - Flask API Server")
print(f"   Host: {HOST}:{PORT}")
print(f"   LLM Backend: {LLM_BACKEND}")
print(f"   LLM Model: {LLM_MODEL}")
print(f"   Agent Mode: {AGENT_MODE}")

if LLM_BACKEND == "ollama" and LLM_PRELOAD_MODEL:
    print(f"🔥 Pre-loading LLM model into VRAM...")
    max_retries = 30
    for i in range(max_retries):
        try:
            requests.get(f"{LLM_HOST}/api/tags", timeout=2)
            requests.post(
                f"{LLM_HOST}/api/generate",
                json={
                    "model": LLM_MODEL, 
                    "prompt": "ping", 
                    "stream": False,
                    "options": {
                        "num_ctx": _getenv_int("LLM_CONTEXT_LENGTH", 2048),
                        "num_parallel": _getenv_int("LLM_NUM_PARALLEL", 4),
                        "num_predict": 1
                    },
                    "keep_alive": getenv("LLM_KEEP_ALIVE", "30m")
                },
                timeout=60
            )
            print(f"✅ Model pre-loaded and ready!")
            break
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"⚠️  Could not pre-load model: {e}")

flask_thread = threading.Thread(target=launch_flask, daemon=True, name="FlaskThread")
flask_thread.start()
print(f"✅ Flask running in dedicated thread: {flask_thread.name}")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n👋 Shutting down...")