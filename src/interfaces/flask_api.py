from flask import Flask # type: ignore
from flask_cors import CORS # type: ignore
from pathlib import Path
from dotenv import load_dotenv # type: ignore
from waitress import serve # type: ignore

load_dotenv()

from .route_handlers.flask_route_handlers import serve_index
from .route_handlers.api.flask_api_route_handlers import flask_api_chat_stream

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
        return default


HOST = getenv("HOST", "0.0.0.0")
PORT = _getenv_int("PORT", 7860)


def launch_flask():
    static_folder = Path(__file__).parent / 'static'
    app = Flask(__name__, static_folder=str(static_folder), static_url_path='')
    CORS(app)  

    app.add_url_rule('/', 'index', serve_index)

    app.add_url_rule('/api/chat/stream', 'chat_stream', flask_api_chat_stream, methods=['POST'])

    serve(app, host=HOST, port=PORT, threads=4)


if __name__ == "__main__":
    launch_flask()