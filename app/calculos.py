"""Cálculo de importes. Siempre en el servidor y con Decimal (nunca float)."""
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
CERO = Decimal("0.00")

# Retención de ISR cuando el cliente es persona moral (honorarios / servicios profesionales)
TASA_ISR = Decimal("0.10")


def redondear(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def tasa_isr_para(tipo_persona):
    """Solo se retiene ISR si quien paga es persona moral."""
    return TASA_ISR if tipo_persona == "M" else Decimal("0")


def calcular_concepto(cantidad, precio_unitario, tasa, tasa_isr=Decimal("0")):
    """Devuelve (importe, iva_importe, isr_importe), cada uno redondeado a centavos."""
    importe = redondear(Decimal(cantidad) * Decimal(precio_unitario))
    iva_importe = redondear(importe * Decimal(tasa))
    isr_importe = redondear(importe * Decimal(tasa_isr))
    return importe, iva_importe, isr_importe


def calcular_totales(conceptos):
    """conceptos: dicts con 'importe', 'iva_importe' e 'isr_importe' ya redondeados.

    Devuelve (subtotal, iva, isr, total) con total = subtotal + IVA - ISR retenido.
    """
    subtotal = sum((c["importe"] for c in conceptos), CERO)
    iva = sum((c["iva_importe"] for c in conceptos), CERO)
    isr = sum((c.get("isr_importe", CERO) for c in conceptos), CERO)
    return redondear(subtotal), redondear(iva), redondear(isr), redondear(subtotal + iva - isr)
