"""Asigna o cambia la contraseña de un usuario desde la terminal.

Uso:  python -m app.asignar_contrasena ana.lopez@sifat.mx

La contraseña se escribe sin mostrarse en pantalla y se guarda cifrada.
Nunca pasa por el chat ni por ningún archivo.
"""
import getpass
import sys

from . import contrasenas
from .config import Config
from .db import transaccion


def main():
    if len(sys.argv) != 2:
        sys.exit("Uso: python -m app.asignar_contrasena correo@dominio.com")
    email = sys.argv[1].strip().lower()
    Config.validar()

    with transaccion() as cur:
        cur.execute("SELECT id_usuario, nombre, rol FROM usuarios WHERE email = %s", (email,))
        usuario = cur.fetchone()
    if not usuario:
        sys.exit(f"No existe un usuario con el correo {email}")

    print(f"Usuario: {usuario['nombre']} ({usuario['rol']})")
    primera = getpass.getpass("Nueva contraseña (mínimo 12, con letras y números): ")
    if not contrasenas.es_robusta(primera):
        sys.exit("La contraseña no cumple: mínimo 12 caracteres, con letras y números.")
    if getpass.getpass("Repítela: ") != primera:
        sys.exit("Las contraseñas no coinciden.")

    with transaccion() as cur:
        cur.execute(
            """UPDATE usuarios SET password_hash = %s, intentos_fallidos = 0,
                   bloqueado_hasta = NULL WHERE id_usuario = %s""",
            (contrasenas.cifrar(primera), usuario["id_usuario"]),
        )
    print("Contraseña guardada (cifrada).")


if __name__ == "__main__":
    main()
