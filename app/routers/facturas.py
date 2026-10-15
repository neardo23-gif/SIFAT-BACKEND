"""Facturas con su detalle. Se crean en una sola transacción y nunca se borran: se cancelan."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..calculos import calcular_concepto, calcular_totales
from ..db import obtener_conexion
from ..errores import ErrorNegocio
from ..esquemas import Cancelacion, FacturaNueva
from ..servicios_client import obtener_servicio

router = APIRouter(prefix="/facturas", tags=["Facturas"])

SELECT_FACTURA = """
    SELECT f.id_factura, f.folio, f.fecha_emision, f.subtotal, f.iva, f.total, f.estatus,
           f.motivo_cancelacion, f.fecha_cancelacion,
           c.id_cliente, c.rfc, c.razon_social AS cliente,
           u.nombre AS usuario,
           fp.clave AS clave_forma_pago, fp.descripcion AS forma_pago,
           mp.clave AS clave_metodo_pago, mp.descripcion AS metodo_pago
    FROM facturas f
    JOIN clientes c ON c.id_cliente = f.id_cliente
    JOIN usuarios u ON u.id_usuario = f.id_usuario
    JOIN formas_pago fp ON fp.id_forma = f.id_forma
    JOIN metodos_pago mp ON mp.id_metodo = f.id_metodo
"""
ESTATUS = {"vigente", "pagada", "cancelada"}


def _uno(cur, sql, params, mensaje):
    cur.execute(sql, params)
    fila = cur.fetchone()
    if not fila:
        raise ErrorNegocio(mensaje)
    return fila


def _detalle_completo(cur, folio):
    cur.execute(SELECT_FACTURA + " WHERE f.folio = %s", (folio,))
    factura = cur.fetchone()
    if not factura:
        raise ErrorNegocio("Factura no encontrada", status=404)
    cur.execute(
        """SELECT id_servicio, clave_servicio, nombre_servicio, cantidad, precio_unitario,
                  importe, tasa_aplicada, iva_importe
           FROM detalle_factura WHERE id_factura = %s ORDER BY id_detalle""",
        (factura["id_factura"],),
    )
    factura["conceptos"] = cur.fetchall()
    cur.execute(
        """SELECT p.id_pago, p.fecha_pago, p.monto, p.referencia, fp.clave AS clave_forma_pago
           FROM pagos p JOIN formas_pago fp ON fp.id_forma = p.id_forma
           WHERE p.id_factura = %s ORDER BY p.fecha_pago""",
        (factura["id_factura"],),
    )
    factura["pagos"] = cur.fetchall()
    pagado = sum((p["monto"] for p in factura["pagos"]), 0)
    factura["saldo"] = factura["total"] - pagado if factura["estatus"] != "cancelada" else 0
    return factura


@router.get("")
def listar(estatus: Optional[str] = None,
           id_cliente: Optional[int] = Query(default=None, gt=0),
           limite: int = Query(default=50, ge=1, le=200),
           desde: int = Query(default=0, ge=0),
           cur=Depends(obtener_conexion)):
    condiciones, params = [], []
    if estatus is not None:
        if estatus not in ESTATUS:
            raise ErrorNegocio("estatus debe ser vigente, pagada o cancelada", status=400)
        condiciones.append("f.estatus = %s")
        params.append(estatus)
    if id_cliente is not None:
        condiciones.append("f.id_cliente = %s")
        params.append(id_cliente)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    cur.execute(SELECT_FACTURA + where + " ORDER BY f.fecha_emision DESC, f.id_factura DESC"
                " LIMIT %s OFFSET %s", (*params, limite, desde))
    filas = cur.fetchall()
    return {"total": len(filas), "facturas": filas}


@router.get("/{folio}")
def obtener(folio: str, cur=Depends(obtener_conexion)):
    return _detalle_completo(cur, folio)


@router.post("", status_code=201)
def crear(datos: FacturaNueva, cur=Depends(obtener_conexion)):
    cliente = _uno(cur, "SELECT id_cliente, activo FROM clientes WHERE id_cliente = %s",
                   (datos.id_cliente,), "El cliente no existe")
    if not cliente["activo"]:
        raise ErrorNegocio("El cliente está inactivo")
    _uno(cur, "SELECT 1 FROM usuarios WHERE id_usuario = %s AND activo = TRUE",
         (datos.id_usuario,), "El usuario no existe o está inactivo")
    id_forma = _uno(cur, "SELECT id_forma AS id FROM formas_pago WHERE clave = %s",
                    (datos.clave_forma_pago,), "La forma de pago no existe")["id"]
    id_metodo = _uno(cur, "SELECT id_metodo AS id FROM metodos_pago WHERE clave = %s",
                     (datos.clave_metodo_pago,), "El método de pago no existe")["id"]

    # Integración SQL/NoSQL: cada servicio se valida contra DynamoDB y se copian
    # sus datos vigentes, así la factura conserva el precio al que se vendió.
    servicios, impuestos, conceptos = {}, {}, []
    for c in datos.conceptos:
        if c.id_servicio not in servicios:
            servicios[c.id_servicio] = obtener_servicio(c.id_servicio)
        s = servicios[c.id_servicio]

        llave = (s["impuesto_nombre"], s["impuesto_tasa"], s["impuesto_tipo"])
        if llave not in impuestos:
            impuestos[llave] = _uno(
                cur, "SELECT id_impuesto AS id FROM impuestos WHERE nombre = %s AND tasa = %s AND tipo = %s",
                llave, f'El impuesto {s["impuesto_nombre"]} {s["impuesto_tasa"]} no está registrado en MySQL',
            )["id"]

        importe, iva_importe = calcular_concepto(c.cantidad, s["precio_unitario"], s["impuesto_tasa"])
        conceptos.append({**s, "cantidad": c.cantidad, "importe": importe,
                          "iva_importe": iva_importe, "id_impuesto": impuestos[llave]})

    subtotal, iva, total = calcular_totales(conceptos)

    # Folio consecutivo a partir del id: primero un folio temporal único
    cur.execute(
        """INSERT INTO facturas (folio, id_cliente, id_usuario, id_forma, id_metodo, subtotal, iva, total)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        ("TMP-" + uuid.uuid4().hex[:16], datos.id_cliente, datos.id_usuario,
         id_forma, id_metodo, subtotal, iva, total),
    )
    id_factura = cur.lastrowid
    folio = f"FAC-{id_factura:04d}"
    cur.execute("UPDATE facturas SET folio = %s WHERE id_factura = %s", (folio, id_factura))

    cur.executemany(
        """INSERT INTO detalle_factura (id_factura, id_servicio, clave_servicio, nombre_servicio,
               cantidad, precio_unitario, importe, id_impuesto, tasa_aplicada, iva_importe)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        [(id_factura, c["id_servicio"], c["clave"], c["nombre"], c["cantidad"],
          c["precio_unitario"], c["importe"], c["id_impuesto"], c["impuesto_tasa"], c["iva_importe"])
         for c in conceptos],
    )
    factura = _detalle_completo(cur, folio)
    cur.connection.commit()
    return factura


@router.post("/{folio}/cancelar")
def cancelar(folio: str, datos: Cancelacion, cur=Depends(obtener_conexion)):
    # FOR UPDATE bloquea la factura para que nadie registre un pago al mismo tiempo
    factura = _uno(cur, "SELECT id_factura, estatus FROM facturas WHERE folio = %s FOR UPDATE",
                   (folio,), "Factura no encontrada")
    if factura["estatus"] != "vigente":
        raise ErrorNegocio(f'Solo se cancelan facturas vigentes (esta está {factura["estatus"]})', status=409)
    cur.execute("SELECT COUNT(*) AS n FROM pagos WHERE id_factura = %s", (factura["id_factura"],))
    if cur.fetchone()["n"]:
        raise ErrorNegocio("La factura tiene pagos registrados y no se puede cancelar", status=409)
    cur.execute(
        """UPDATE facturas SET estatus = 'cancelada', motivo_cancelacion = %s,
               fecha_cancelacion = CURRENT_TIMESTAMP WHERE id_factura = %s""",
        (datos.motivo, factura["id_factura"]),
    )
    resultado = _detalle_completo(cur, folio)
    cur.connection.commit()
    return resultado
