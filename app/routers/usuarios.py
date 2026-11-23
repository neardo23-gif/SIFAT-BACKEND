"""Usuarios de la app. Los administra un Administrador desde el front (protegido con X-API-Key).

En la tabla, nombre y apellidos se guardan juntos en `nombre` (VARCHAR 100), igual que los
usuarios iniciales. La contraseña se guarda cifrada con PBKDF2 y nunca se devuelve.
Los usuarios no se borran (tienen facturas ligadas): se desactivan.
"""
import unicodedata

import pymysql
from fastapi import APIRouter, Depends

from .. import contrasenas
from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import ContrasenaNueva, UsuarioCambios, UsuarioNuevo

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


def _obtener(cur, id_usuario):
    cur.execute(SELECT_USUARIO + " WHERE id_usuario = %s", (id_usuario,))
    fila = cur.fetchone()
    if not fila:
        raise ErrorNegocio("Usuario no encontrado", status=404)
    return _limpiar(fila)


def _plano(texto):
    """Minúsculas y sin acentos, para que "Pérez" y "perez" cuenten igual."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c))


def validar_contrasena(password, nombre, email):
    """Reglas de robustez. Lanza ErrorNegocio con el motivo en español."""
    if not contrasenas.es_robusta(password):
        raise ErrorNegocio(f"La contraseña debe tener al menos {contrasenas.LONGITUD_MINIMA} caracteres, "
                           "con letras y números")
    texto = _plano(password)
    usuario_correo = _plano(email.split("@")[0])
    partes_nombre = [p for p in _plano(nombre).replace("-", " ").split() if len(p) >= 4]
    if (len(usuario_correo) >= 4 and usuario_correo in texto) or any(p in texto for p in partes_nombre):
        raise ErrorNegocio("La contraseña no puede contener tu nombre ni tu correo")
    if len(set(password)) < 5:
        raise ErrorNegocio("La contraseña es demasiado repetitiva: usa más caracteres distintos")


def guardar_contrasena(cur, id_usuario, password):
    """Cifra y guarda; además desbloquea la cuenta y reinicia los intentos fallidos."""
    cur.execute(
        """UPDATE usuarios SET password_hash = %s, intentos_fallidos = 0, bloqueado_hasta = NULL
           WHERE id_usuario = %s""",
        (contrasenas.cifrar(password), id_usuario),
    )


@router.get("")
def listar(cur=Depends(obtener_conexion)):
    cur.execute(SELECT_USUARIO + " ORDER BY nombre")
    filas = [_limpiar(f) for f in cur.fetchall()]
    return {"total": len(filas), "usuarios": filas}


@router.get("/{id_usuario}")
def obtener(id_usuario: int, cur=Depends(obtener_conexion)):
    return _obtener(cur, id_usuario)


@router.post("", status_code=201)
def crear(datos: UsuarioNuevo, cur=Depends(obtener_conexion)):
    nombre_completo = f"{datos.nombre} {datos.apellidos}"
    if len(nombre_completo) > 100:
        raise ErrorNegocio("Nombre y apellidos juntos no pueden pasar de 100 caracteres")
    email = datos.email.lower()
    validar_contrasena(datos.password, nombre_completo, email)

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
    usuario = _obtener(cur, cur.lastrowid)
    cur.connection.commit()
    return usuario


@router.patch("/{id_usuario}")
def modificar(id_usuario: int, datos: UsuarioCambios, cur=Depends(obtener_conexion)):
    """Activa/desactiva o cambia el rol. Nunca deja la app sin un Administrador activo."""
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        raise ErrorNegocio("No se enviaron campos para modificar", status=400)
    # FOR UPDATE: dos administradores no pueden desactivarse mutuamente a la vez
    cur.execute("SELECT id_usuario, rol, activo FROM usuarios WHERE id_usuario = %s FOR UPDATE",
                (id_usuario,))
    actual = cur.fetchone()
    if not actual:
        raise ErrorNegocio("Usuario no encontrado", status=404)

    deja_de_ser_admin = actual["rol"] == "Administrador" and bool(actual["activo"]) and (
        cambios.get("activo") is False or cambios.get("rol", "Administrador") != "Administrador")
    if deja_de_ser_admin:
        cur.execute("""SELECT COUNT(*) AS n FROM usuarios
                       WHERE rol = 'Administrador' AND activo = TRUE AND id_usuario <> %s FOR UPDATE""",
                    (id_usuario,))
        if cur.fetchone()["n"] == 0:
            raise ErrorNegocio("Debe quedar al menos un Administrador activo", status=409)

    # Columnas de una lista fija; los valores van como parámetros
    columnas = [c for c in ("activo", "rol") if c in cambios]
    sets = ", ".join(f"{c} = %s" for c in columnas)
    cur.execute(f"UPDATE usuarios SET {sets} WHERE id_usuario = %s",
                (*(cambios[c] for c in columnas), id_usuario))
    usuario = _obtener(cur, id_usuario)
    cur.connection.commit()
    return usuario


@router.post("/{id_usuario}/contrasena")
def restablecer_contrasena(id_usuario: int, datos: ContrasenaNueva, cur=Depends(obtener_conexion)):
    """Un Administrador pone una contraseña nueva (por ejemplo, si el usuario la olvidó)."""
    usuario = _obtener(cur, id_usuario)
    validar_contrasena(datos.password, usuario["nombre"], usuario["email"])
    guardar_contrasena(cur, id_usuario, datos.password)
    cur.connection.commit()
    return {"mensaje": "Contraseña actualizada"}
