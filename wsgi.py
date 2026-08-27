"""WSGI entry point for a production server.

    gunicorn wsgi:app          (Linux / most hosts)
    waitress-serve --port=5000 wsgi:app     (Windows)

Never run `python app.py` for anything public — that is Flask's development
server: single-threaded, unencrypted, and explicitly not built to face the
internet.
"""

from app import app  # noqa: F401  (importing app also runs bootstrap())
