"""Cálculo de importes. Siempre en el servidor y con Decimal (nunca float)."""
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def redondear(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_concepto(cantidad, precio_unitario, tasa):
    importe = redondear(Decimal(cantidad) * Decimal(precio_unitario))
    iva_importe = redondear(importe * Decimal(tasa))
    return importe, iva_importe


def calcular_totales(conceptos):
    """conceptos: lista de dicts con 'importe' e 'iva_importe' ya redondeados."""
    subtotal = sum((c["importe"] for c in conceptos), Decimal("0.00"))
    iva = sum((c["iva_importe"] for c in conceptos), Decimal("0.00"))
    return redondear(subtotal), redondear(iva), redondear(subtotal + iva)
