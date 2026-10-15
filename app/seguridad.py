"""Autenticación del frontend con una clave compartida (header X-API-Key)."""
import hmac

from fastapi import Header, HTTPException

from .config import Config


def requiere_api_key(x_api_key: str = Header(default="")):
    # compare_digest evita ataques por tiempo de respuesta
    if not x_api_key or not hmac.compare_digest(x_api_key, Config.BACKEND_API_KEY):
        raise HTTPException(status_code=401, detail="Clave de acceso inválida o ausente")
