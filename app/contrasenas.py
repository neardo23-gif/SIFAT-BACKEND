"""Cifrado de contraseñas con PBKDF2-SHA256 (biblioteca estándar, sin dependencias).

Formato guardado: pbkdf2_sha256$<iteraciones>$<sal_hex>$<hash_hex>
"""
import hashlib
import hmac
import secrets

ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 600_000  # recomendación OWASP para PBKDF2-SHA256
LONGITUD_MINIMA = 12

# Hash de una contraseña que nadie conoce: se verifica contra él cuando el correo
# no existe, para que la respuesta tarde lo mismo y no delate qué correos existen.
_HASH_SEÑUELO = None


def cifrar(contrasena):
    sal = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, ITERACIONES)
    return f"{ALGORITMO}${ITERACIONES}${sal.hex()}${digest.hex()}"


def verificar(contrasena, guardado):
    try:
        algoritmo, iteraciones, sal, digest = guardado.split("$")
        if algoritmo != ALGORITMO:
            return False
        calculado = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"),
                                        bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(calculado.hex(), digest)
    except (ValueError, AttributeError):
        return False


def verificar_señuelo(contrasena):
    global _HASH_SEÑUELO
    if _HASH_SEÑUELO is None:
        _HASH_SEÑUELO = cifrar(secrets.token_urlsafe(16))
    verificar(contrasena, _HASH_SEÑUELO)
    return False


def es_robusta(contrasena):
    """Mínimo 12 caracteres con letras y números."""
    return (len(contrasena) >= LONGITUD_MINIMA
            and any(c.isalpha() for c in contrasena)
            and any(c.isdigit() for c in contrasena))
