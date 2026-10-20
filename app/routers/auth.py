"""Inicio de sesión. Lo llama solo el servidor del frontend (protegido con X-API-Key)."""
from fastapi import APIRouter, Depends
from pydantic import Field

from .. import contrasenas
from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import EMAIL, Estricto

router = APIRouter(prefix="/auth", tags=["Autenticación"])

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
MENSAJE_GENERICO = "Correo o contraseña incorrectos"


class Credenciales(Estricto):
    email: str = Field(max_length=120, pattern=EMAIL)
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def login(datos: Credenciales, cur=Depends(obtener_conexion)):
    cur.execute(
        """SELECT id_usuario, nombre, email, rol, activo, password_hash,
                  intentos_fallidos, bloqueado_hasta > CURRENT_TIMESTAMP AS bloqueado
           FROM usuarios WHERE email = %s FOR UPDATE""",
        (datos.email.lower(),),
    )
    usuario = cur.fetchone()

    # Mismo mensaje y mismo tiempo de respuesta si el correo no existe,
    # está inactivo o no tiene contraseña: no se revela qué cuentas existen.
    if not usuario or not usuario["activo"] or not usuario["password_hash"]:
        contrasenas.verificar_señuelo(datos.password)
        raise ErrorNegocio(MENSAJE_GENERICO, status=401)

    if usuario["bloqueado"]:
        contrasenas.verificar_señuelo(datos.password)
        raise ErrorNegocio(f"Cuenta bloqueada por intentos fallidos. Intenta en {MINUTOS_BLOQUEO} minutos.",
                           status=423)

    if not contrasenas.verificar(datos.password, usuario["password_hash"]):
        intentos = usuario["intentos_fallidos"] + 1
        if intentos >= MAX_INTENTOS:
            cur.execute(
                """UPDATE usuarios SET intentos_fallidos = 0,
                       bloqueado_hasta = CURRENT_TIMESTAMP + INTERVAL %s MINUTE
                   WHERE id_usuario = %s""",
                (MINUTOS_BLOQUEO, usuario["id_usuario"]),
            )
        else:
            cur.execute("UPDATE usuarios SET intentos_fallidos = %s WHERE id_usuario = %s",
                        (intentos, usuario["id_usuario"]))
        cur.connection.commit()  # el contador se guarda aunque se responda con error
        raise ErrorNegocio(MENSAJE_GENERICO, status=401)

    cur.execute(
        """UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL,
               ultimo_acceso = CURRENT_TIMESTAMP WHERE id_usuario = %s""",
        (usuario["id_usuario"],),
    )
    cur.connection.commit()
    return {"id_usuario": usuario["id_usuario"], "nombre": usuario["nombre"],
            "email": usuario["email"], "rol": usuario["rol"]}
