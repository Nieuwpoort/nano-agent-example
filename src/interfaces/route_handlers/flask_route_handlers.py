from flask import send_from_directory # type: ignore
from pathlib import Path

def serve_index(): return send_from_directory(str(Path(__file__).parent.parent / "views"), "index.html")