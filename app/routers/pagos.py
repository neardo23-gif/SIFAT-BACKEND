"""Pagos. El monto nunca puede superar el saldo; al liquidarse, la factura pasa a 'pagada'."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import PagoNuevo

router = APIRouter(prefix="/pagos", tags=["Pagos"])

SELECT_PAGO = """
    SELECT p.id_pago, f.folio, c.razon_social AS cliente, p.fecha_pago, p.monto, p.referencia,
           fp.clave AS clave_forma_pago, fp.descripcion AS forma_pago
    FROM pagos p
    JOIN facturas f ON f.id_factura = p.id_factura
    JOIN clientes c ON c.id_cliente = f.id_cliente
    JOIN formas_pago fp ON fp.id_forma = p.id_forma
"""


@router.get("")
def listar(folio: Optional[str] = Query(default=None, pattern=r"^FAC-\d{4,10}$"),
           limite: int = Query(default=50, ge=1, le=200),
           desde: int = Query(default=0, ge=0),
           cur=Depends(obtener_conexion)):
    where, params = ("", ()) if folio is None else (" WHERE f.folio = %s", (folio,))
    cur.execute(SELECT_PAGO + where + " ORDER BY p.fecha_pago DESC, p.id_pago DESC LIMIT %s OFFSET %s",
                (*params, limite, desde))
    filas = cur.fetchall()
    return {"total": len(filas), "pagos": filas}


@router.post("", status_code=201)
def registrar(datos: PagoNuevo, cur=Depends(obtener_conexion)):
    # FOR UPDATE: dos pagos simultáneos no pueden rebasar el saldo
    cur.execute("SELECT id_factura, total, estatus FROM facturas WHERE folio = %s FOR UPDATE",
                (datos.folio,))
    factura = cur.fetchone()
    if not factura:
        raise ErrorNegocio("Factura no encontrada", status=404)
    if factura["estatus"] != "vigente":
        raise ErrorNegocio(f'La factura está {factura["estatus"]}: no admite pagos', status=409)

    cur.execute("SELECT id_forma FROM formas_pago WHERE clave = %s", (datos.clave_forma_pago,))
    forma = cur.fetchone()
    if not forma:
        raise ErrorNegocio("La forma de pago no existe")

    cur.execute("SELECT COALESCE(SUM(monto), 0) AS pagado FROM pagos WHERE id_factura = %s",
                (factura["id_factura"],))
    saldo = factura["total"] - cur.fetchone()["pagado"]
    if datos.monto > saldo:
        raise ErrorNegocio(f"El monto excede el saldo pendiente ({saldo})")

    cur.execute(
        "INSERT INTO pagos (id_factura, id_forma, monto, referencia) VALUES (%s, %s, %s, %s)",
        (factura["id_factura"], forma["id_forma"], datos.monto, datos.referencia),
    )
    id_pago = cur.lastrowid
    nuevo_saldo = saldo - datos.monto
    if nuevo_saldo == 0:
        cur.execute("UPDATE facturas SET estatus = 'pagada' WHERE id_factura = %s",
                    (factura["id_factura"],))

    cur.execute(SELECT_PAGO + " WHERE p.id_pago = %s", (id_pago,))
    pago = cur.fetchone()
    pago["saldo_restante"] = nuevo_saldo
    pago["factura_pagada"] = nuevo_saldo == 0
    cur.connection.commit()
    return pago
