"""Cliente del catálogo de servicios (API Gateway + Lambda + DynamoDB)."""
import re
from decimal import Decimal

import requests

from .config import Config
from .errores import ErrorNegocio, ErrorServicioExterno

ID_SERVICIO_RE = re.compile(r"^SRV-\d{3,6}$")


def obtener_servicio(id_servicio):
    """Devuelve el servicio activo o lanza ErrorNegocio si no existe o está dado de baja."""
    if not ID_SERVICIO_RE.match(id_servicio):
        raise ErrorNegocio(f'El servicio "{id_servicio}" tiene un formato inválido')
    try:
        r = requests.get(
            f"{Config.SERVICIOS_API_URL}/servicios",
            params={"id_servicio": id_servicio},
            headers={"x-api-key": Config.SERVICIOS_API_KEY},
            timeout=8,
        )
    except requests.RequestException as exc:
        raise ErrorServicioExterno(f"Catálogo no disponible ({exc.__class__.__name__})")

    if r.status_code == 404:
        raise ErrorNegocio(f'El servicio "{id_servicio}" no existe o fue dado de baja')
    if r.status_code != 200:
        raise ErrorServicioExterno(f"El catálogo respondió {r.status_code}")

    s = r.json(parse_float=Decimal)
    impuesto = s.get("impuesto") or {}
    if not s.get("activo", False):
        raise ErrorNegocio(f'El servicio "{id_servicio}" no está activo')
    if not {"nombre", "tasa", "tipo"} <= set(impuesto):
        raise ErrorNegocio(f'El servicio "{id_servicio}" no tiene un impuesto válido')
    return {
        "id_servicio": s["id_servicio"],
        "clave": s["clave"],
        "nombre": s["nombre"],
        "precio_unitario": Decimal(str(s["precio_unitario"])),
        "impuesto_nombre": impuesto["nombre"],
        "impuesto_tasa": Decimal(str(impuesto["tasa"])),
        "impuesto_tipo": impuesto["tipo"],
    }
