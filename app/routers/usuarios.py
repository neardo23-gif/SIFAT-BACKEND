"""Usuarios de la app. Los da de alta un Administrador desde el front (protegido con X-API-Key).

En la tabla, nombre y apellidos se guardan juntos en `nombre` (VARCHAR 100), igual que los
usuarios iniciales. La contraseña se guarda cifrada con PBKDF2 y nunca se devuelve.
"""
import pymysql
from fastapi import APIRouter, Depends

from .. import contrasenas
from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import UsuarioNuevo

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

SELECT_USUARIO = """
    SELECT id_usuario, nombre, email, rol, activo, ultimo_acceso,
           password_hash IS NOT NULL AS tiene_contrasena
    FROM usuarios
"""


def _limpiar(fila):
    fila["activo"] = bool(fila["activo"])
    fila["tiene_contrasena"] = bool(fila["tiene_contrasena"])
    return fila


@router.get("")
def listar(cur=Depends(obtener_conexion)):
    cur.execute(SELECT_USUARIO + " ORDER BY nombre")
    filas = [_limpiar(f) for f in cur.fetchall()]
    return {"total": len(filas), "usuarios": filas}


def _validar_contrasena(datos):
    p = datos.password
    if not contrasenas.es_robusta(p):
        raise ErrorNegocio(f"La contraseña debe tener al menos {contrasenas.LONGITUD_MINIMA} caracteres, "
                           "con letras y números")
    texto = p.lower()
    usuario_correo = datos.email.split("@")[0].lower()
    nombre = datos.nombre.lower()
    if (len(usuario_correo) >= 4 and usuario_correo in texto) or (len(nombre) >= 4 and nombre in texto):
        raise ErrorNegocio("La contraseña no puede contener tu nombre ni tu correo")
    if len(set(p)) < 5:
        raise ErrorNegocio("La contraseña es demasiado repetitiva: usa más caracteres distintos")


@router.post("", status_code=201)
def crear(datos: UsuarioNuevo, cur=Depends(obtener_conexion)):
    nombre_completo = f"{datos.nombre} {datos.apellidos}"
    if len(nombre_completo) > 100:
        raise ErrorNegocio("Nombre y apellidos juntos no pueden pasar de 100 caracteres")
    _validar_contrasena(datos)

    email = datos.email.lower()
    cur.execute("SELECT 1 FROM usuarios WHERE email = %s", (email,))
    if cur.fetchone():
        raise ErrorNegocio("Ya existe un usuario con ese correo", status=409)
    try:
        cur.execute(
            """INSERT INTO usuarios (nombre, email, password_hash, rol, activo)
               VALUES (%s, %s, %s, %s, TRUE)""",
            (nombre_completo, email, contrasenas.cifrar(datos.password), datos.rol),
        )
    except pymysql.err.IntegrityError:
        # Dos altas simultáneas con el mismo correo: la llave UNIQUE decide
        raise ErrorNegocio("Ya existe un usuario con ese correo", status=409)
    id_usuario = cur.lastrowid
    cur.execute(SELECT_USUARIO + " WHERE id_usuario = %s", (id_usuario,))
    usuario = _limpiar(cur.fetchone())
    cur.connection.commit()
    return usuario
