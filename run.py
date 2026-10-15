"""Arranque local: python run.py  (escucha solo en 127.0.0.1)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:crear_app", factory=True, host="127.0.0.1",
                port=int(os.getenv("PORT", "8000")), reload=False)
