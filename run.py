"""Entry point: py run.py  →  CineBite on http://localhost:8000"""
import uvicorn

from app.config import HOST, PORT

if __name__ == "__main__":
    print(f"\n  🍿 CineBite running at http://localhost:{PORT}\n")
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="info")
