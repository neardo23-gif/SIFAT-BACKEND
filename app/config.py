"""Configuración leída del entorno (.env). Ningún secreto vive en el código."""
import os

from dotenv import load_dotenv

load_dotenv()


def _requerida(nombre):
    valor = os.getenv(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (revisa tu .env)")
    return valor


class Config:
    DB_HOST = os.getenv("DB_HOST", "").strip()
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "sifat").strip()
    DB_USER = os.getenv("DB_USER", "").strip()
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_SSL_CA = os.getenv("DB_SSL_CA", "").strip()

    SERVICIOS_API_URL = os.getenv("SERVICIOS_API_URL", "").strip().rstrip("/")
    SERVICIOS_API_KEY = os.getenv("SERVICIOS_API_KEY", "").strip()

    BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "").strip()
    ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"

    @classmethod
    def validar(cls):
        """Falla al arrancar si falta algo crítico, en lugar de fallar a media petición."""
        for nombre in ("DB_HOST", "DB_USER", "DB_PASSWORD", "SERVICIOS_API_URL",
                       "SERVICIOS_API_KEY", "BACKEND_API_KEY"):
            _requerida(nombre)
        if cls.DB_USER == "admin":
            raise RuntimeError("No uses el usuario admin en la aplicación: usa sifat_app")
        if len(cls.BACKEND_API_KEY) < 24:
            raise RuntimeError("BACKEND_API_KEY debe tener al menos 24 caracteres")
        if not cls.DB_SSL_CA or not os.path.isfile(cls.DB_SSL_CA):
            raise RuntimeError("DB_SSL_CA debe apuntar al certificado de AWS (ver README)")
