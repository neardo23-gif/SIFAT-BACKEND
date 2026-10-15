"""Validación estricta de entrada. extra='forbid' rechaza cualquier campo no declarado."""
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

RFC = r"^([A-ZÑ&]{3,4})\d{6}([A-Z\d]{3})$"
CP = r"^\d{5}$"
TELEFONO = r"^\d{10,15}$"
EMAIL = r"^[^@\s]{1,64}@[^@\s]{1,120}\.[A-Za-z]{2,24}$"
TEXTO_SEGURO = r"^[^\x00-\x1f]*$"  # sin caracteres de control


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------- Clientes ----------------
class ClienteNuevo(Estricto):
    rfc: str = Field(pattern=RFC, min_length=12, max_length=13)
    razon_social: str = Field(min_length=1, max_length=200, pattern=TEXTO_SEGURO)
    cp_fiscal: str = Field(pattern=CP)
    clave_regimen: str = Field(pattern=r"^\d{3}$")
    clave_uso: str = Field(pattern=r"^[A-Z]\d{2}$|^CN01$|^CP01$")
    email: Optional[str] = Field(default=None, max_length=120, pattern=EMAIL)
    telefono: Optional[str] = Field(default=None, pattern=TELEFONO)


class ClienteCambios(Estricto):
    razon_social: Optional[str] = Field(default=None, min_length=1, max_length=200, pattern=TEXTO_SEGURO)
    cp_fiscal: Optional[str] = Field(default=None, pattern=CP)
    clave_regimen: Optional[str] = Field(default=None, pattern=r"^\d{3}$")
    clave_uso: Optional[str] = Field(default=None, pattern=r"^[A-Z]\d{2}$|^CN01$|^CP01$")
    email: Optional[str] = Field(default=None, max_length=120, pattern=EMAIL)
    telefono: Optional[str] = Field(default=None, pattern=TELEFONO)
    activo: Optional[bool] = None


# ---------------- Facturas ----------------
class ConceptoNuevo(Estricto):
    id_servicio: str = Field(pattern=r"^SRV-\d{3,6}$")
    cantidad: Decimal = Field(gt=0, le=Decimal("99999999.99"), decimal_places=2)


class FacturaNueva(Estricto):
    id_cliente: int = Field(gt=0)
    id_usuario: int = Field(gt=0)
    clave_forma_pago: str = Field(pattern=r"^\d{2}$")
    clave_metodo_pago: str = Field(pattern=r"^(PUE|PPD)$")
    conceptos: List[ConceptoNuevo] = Field(min_length=1, max_length=100)


class Cancelacion(Estricto):
    motivo: str = Field(min_length=5, max_length=255, pattern=TEXTO_SEGURO)


# ---------------- Pagos ----------------
class PagoNuevo(Estricto):
    folio: str = Field(pattern=r"^FAC-\d{4,10}$")
    clave_forma_pago: str = Field(pattern=r"^\d{2}$")
    monto: Decimal = Field(gt=0, le=Decimal("9999999999.99"), decimal_places=2)
    referencia: Optional[str] = Field(default=None, max_length=100, pattern=TEXTO_SEGURO)
