"""Catálogos fiscales del SAT y usuarios (solo lectura)."""
from fastapi import APIRouter, Depends

from ..db import obtener_conexion

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])

# Nombres fijos: nunca se arma el nombre de la tabla con datos del usuario
CONSULTAS = {
    "regimenes": "SELECT clave, descripcion, tipo_persona FROM regimenes_fiscales ORDER BY clave",
    "usos-cfdi": "SELECT clave, descripcion FROM usos_cfdi ORDER BY clave",
    "formas-pago": "SELECT clave, descripcion FROM formas_pago ORDER BY clave",
    "metodos-pago": "SELECT clave, descripcion FROM metodos_pago ORDER BY clave",
    "impuestos": "SELECT nombre, tasa, tipo FROM impuestos ORDER BY nombre, tasa",
    "usuarios": "SELECT id_usuario, nombre, rol FROM usuarios WHERE activo = TRUE ORDER BY nombre",
}


@router.get("")
def todos(cur=Depends(obtener_conexion)):
    resultado = {}
    for nombre, sql in CONSULTAS.items():
        cur.execute(sql)
        resultado[nombre] = cur.fetchall()
    return resultado
