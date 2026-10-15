"""Conexión a MySQL (RDS). Toda consulta usa parámetros: nunca se concatena SQL."""
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from .config import Config


def conectar():
    return pymysql.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=8,
        read_timeout=15,
        write_timeout=15,
        # Conexión cifrada y verificación del certificado del servidor
        ssl={"ca": Config.DB_SSL_CA},
        ssl_verify_cert=True,
        ssl_verify_identity=True,
    )


@contextmanager
def transaccion():
    """Abre una conexión; hace COMMIT si todo sale bien y ROLLBACK si algo falla."""
    conn = conectar()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obtener_conexion():
    """Dependencia de FastAPI: una transacción por petición.

    Las rutas que escriben hacen cur.connection.commit() antes de responder, para
    que el cliente nunca reciba un 201 de algo que no quedó guardado. Si la ruta
    lanza un error, aquí se hace ROLLBACK.
    """
    with transaccion() as cur:
        yield cur
